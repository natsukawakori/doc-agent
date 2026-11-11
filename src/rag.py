"""DuReader 全语料向量召回、正文读取和本地交叉编码器重排。"""
import gzip
import json
import os
import struct
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data" / "dureader"
CACHE = DATA / "bge_full_cache"
CORPUS = DATA / "passage_collection.tsv.gz"
LOOKUP = DATA / "passage_lookup"
MODEL = "BAAI/bge-small-zh-v1.5"
MODEL_REV = "7999e1d3359715c523056ef9478215996d62a620"
RERANKER = "BAAI/bge-reranker-base"
RERANKER_REV = "2cfc18c9415c912f9d8155881c133215df768a70"
PREFIX = "为这个句子生成表示以用于检索相关文章："
os.environ.setdefault("HF_HOME", str(PROJECT / "data" / "huggingface"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


def retrieve_many(queries, top_k=50):
    import torch
    from sentence_transformers import SentenceTransformer

    manifest = json.loads((CACHE / "manifest.json").read_text(encoding="utf-8"))
    if (manifest["model"], manifest["model_revision"], manifest["dimension"],
            manifest["max_seq_length"]) != (MODEL, MODEL_REV, 512, 256):
        raise ValueError("向量缓存与模型配置不匹配")
    count = manifest["count"]
    precision = os.getenv("DOC_AGENT_VECTOR_DTYPE", "float32").strip().lower()
    if precision not in ("float32", "float16"):
        raise ValueError("DOC_AGENT_VECTOR_DTYPE 必须为 float32 或 float16")
    if precision == "float16":
        half = json.loads((CACHE / "manifest_f16.json").read_text(encoding="utf-8"))
        if (half["source_sha256"] != manifest["vectors_sha256"] or half["count"] != count or
                half["ids_sha256"] != manifest["ids_sha256"] or half["dimension"] != 512):
            raise ValueError("半精度缓存与原向量不匹配")
        vector_path, vector_dtype, width = CACHE / half["vectors_file"], "<f2", 2
    else:
        vector_path, vector_dtype, width = CACHE / manifest["vectors_file"], "<f4", 4
    ids_path = CACHE / manifest["ids_file"]
    if vector_path.stat().st_size != count * 512 * width or ids_path.stat().st_size != count * 32:
        raise ValueError("向量缓存文件长度异常")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    if device == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = False
    model = SentenceTransformer(MODEL, revision=MODEL_REV, device=device)
    model.max_seq_length = 256
    backend = os.getenv("DOC_AGENT_VECTOR_BACKEND", "faiss").strip().lower()
    if backend not in ("faiss", "torch"):
        raise ValueError("DOC_AGENT_VECTOR_BACKEND 必须为 faiss 或 torch")
    with torch.inference_mode():
        q = model.encode([PREFIX + query for query in queries], normalize_embeddings=True, convert_to_tensor=True)
        if backend == "faiss":
            from src.faiss_scan import scan
            positions, scores = scan(q.cpu().numpy(), vector_path, vector_dtype, width, count, top_k)
        else:
            from src.torch_scan import scan
            positions, scores = scan(q, vector_path, vector_dtype, width, count, top_k, device)
    with ids_path.open("rb") as f:
        results = []
        for positions_row, scores_row in zip(positions, scores):
            row = []
            for position, score in zip(positions_row, scores_row):
                f.seek(position * 32)
                row.append({"id": f.read(32).decode("ascii"), "dense_score": float(score),
                            "ordinal": int(position)})
            results.append(row)
    return results, device


def retrieve(query, top_k=50):
    rows, device = retrieve_many([query], top_k)
    return rows[0], device


def get_passages(ids, positions=None):
    if positions is not None and (LOOKUP / "manifest.json").exists():
        return lookup_passages(ids, positions)
    missing, found = set(ids), {}
    with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
        for line in f:
            pid, sep, text = line.rstrip("\r\n").partition("\t")
            if sep and pid in missing:
                found[pid] = text
                missing.remove(pid)
                if not missing:
                    break
    if missing:
        raise ValueError(f"语料中找不到 {len(missing)} 个候选段落")
    return found


def lookup_passages(ids, positions):
    meta = json.loads((LOOKUP / "manifest.json").read_text(encoding="utf-8"))
    vectors = json.loads((CACHE / "manifest.json").read_text(encoding="utf-8"))
    if (meta["count"] != vectors["count"] or meta["corpus_sha256"] != vectors["corpus_sha256"]
            or meta["ids_sha256"] != vectors["ids_sha256"] or len(ids) != len(positions)):
        raise ValueError("正文索引与向量缓存不匹配")
    if ((LOOKUP / "offsets.u64").stat().st_size != meta["count"] * 8 or
            (LOOKUP / "passages.tsv").stat().st_size != meta["text_bytes"]):
        raise ValueError("正文索引文件长度异常")
    found = {}
    with (LOOKUP / "offsets.u64").open("rb") as offsets, (LOOKUP / "passages.tsv").open("rb") as texts:
        for pid, position in zip(ids, positions):
            if not 0 <= position < meta["count"]:
                raise ValueError("正文位置超出范围")
            offsets.seek(position * 8)
            raw_offset = offsets.read(8)
            if len(raw_offset) != 8:
                raise ValueError("正文索引不完整")
            texts.seek(struct.unpack("<Q", raw_offset)[0])
            line = texts.readline()
            raw_id, sep, text = line.rstrip(b"\r\n").partition(b"\t")
            if not sep or raw_id.decode("ascii") != pid:
                raise ValueError("正文段落 ID 与检索结果不一致")
            found[pid] = text.decode("utf-8")
    return found


def search_many(queries, top_k=5):
    if (not isinstance(queries, list) or not 1 <= len(queries) <= 8 or
            any(not isinstance(query, str) or not query.strip() for query in queries) or not 1 <= top_k <= 50):
        raise ValueError("需要 1 到 8 个非空查询，且 top_k 必须为 1 到 50")
    from sentence_transformers import CrossEncoder
    queries = [query.strip() for query in queries]
    rows, device = retrieve_many(queries, top_k=50)
    candidates = [candidate for row in rows for candidate in row]
    texts = get_passages([x["id"] for x in candidates], [x["ordinal"] for x in candidates])
    reranker = CrossEncoder(RERANKER, revision=RERANKER_REV, max_length=384, device=device)
    pairs = [(query, texts[x["id"]][:8000]) for query, row in zip(queries, rows) for x in row]
    scores = reranker.predict(pairs, batch_size=4, show_progress_bar=False)
    for item, score in zip(candidates, scores):
        item["rerank_score"] = float(score)
    for row in rows:
        row.sort(key=lambda x: x["rerank_score"], reverse=True)
    return [[{"source": "DuReader:" + x["id"], "text": texts[x["id"]][:1600],
              "dense_score": x["dense_score"], "rerank_score": x["rerank_score"]}
             for x in row[:top_k]] for row in rows]


def search(query, top_k=5):
    return search_many([query], top_k)[0]


def main():
    import sys
    if len(sys.argv) < 3 or sys.argv[1] != "search":
        print('用法：python -m src.rag search "问题"')
        return
    print(json.dumps(search(" ".join(sys.argv[2:])), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
