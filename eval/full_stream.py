"""逐批扫描完整 DuReader 语料并在内存受限环境中精确检索。"""
import argparse
import gzip
import hashlib
import itertools
import json
import os
import time
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parent.parent / "data" / "huggingface"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import torch
from sentence_transformers import SentenceTransformer
from eval.process_memory import memory
from eval.full_report import write_result
from eval.stream_rank import StreamingTopK
from eval.vector_cache import VectorCache
from eval.full_guard import pace

PROJECT = Path(__file__).resolve().parent.parent
MODEL = "BAAI/bge-small-zh-v1.5"
REVISION = "7999e1d3359715c523056ef9478215996d62a620"
PREFIX = "为这个句子生成表示以用于检索相关文章："
CORPUS_SHA = "4c185a9d143488043d0ed64cc425d21ff5cf56edb5fc75f7939f867218ae6a69"
GROUP = 256
CHECKPOINT_EVERY = 4096


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        while block := f.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def save_checkpoint(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("queries", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--cache-dir", type=Path, default=Path("data/dureader/bge_full_cache"))
    parser.add_argument("--pause-seconds", type=float, default=0.5)
    parser.add_argument("--temp-limit", type=float, default=83)
    parser.add_argument("--pilot", type=int, default=0, help="只处理前 N 行测吞吐，不产生正式评测结果")
    args = parser.parse_args()
    if args.batch_size < 1 or args.pilot < 0 or not 0 <= args.pause_seconds <= 10 or not 60 <= args.temp_limit <= 90:
        raise ValueError("批次大小或试运行行数不合法")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用，请检查 GPU 环境")
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    if args.device == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.cuda.reset_peak_memory_stats()
    query_hash = sha256(args.queries)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    data = json.loads(args.queries.read_text(encoding="utf-8"))
    queries = data["queries"]
    if query_hash != manifest["queries_sha256"] or len(queries) != 100:
        raise ValueError("测试题与已冻结清单不匹配")
    if manifest["model_revision"] != REVISION or manifest["corpus_sha256"] != CORPUS_SHA:
        raise ValueError("清单里的模型或语料版本不匹配")
    if not args.pilot:
        if args.output.exists():
            raise FileExistsError("正式结果已存在，拒绝覆盖；请使用缓存检索或另选输出路径")
        print("正在核验完整语料 SHA256……", flush=True)
        if sha256(args.corpus) != CORPUS_SHA:
            raise ValueError("完整语料哈希不匹配")
    signature = {"queries_sha256": query_hash, "corpus_sha256": CORPUS_SHA,
                 "model": MODEL, "model_revision": REVISION, "max_seq_length": 256,
                 "prefix": PREFIX, "device": args.device, "torch_version": torch.__version__,
                 "batch_size": args.batch_size, "group_size": GROUP,
                 "engine_sha256": sha256(__file__),
                 "ranker_sha256": sha256(PROJECT / "eval" / "stream_rank.py"),
                 "cache_code_sha256": sha256(PROJECT / "eval" / "vector_cache.py"),
                 "guard_code_sha256": sha256(PROJECT / "eval" / "full_guard.py"),
                 "memory_code_sha256": sha256(PROJECT / "eval" / "process_memory.py"),
                 "cache_dir": str(args.cache_dir.resolve()), "pause_seconds": args.pause_seconds,
                 "temp_limit": args.temp_limit}
    prior = None
    if not args.pilot and args.checkpoint.exists():
        prior = json.loads(args.checkpoint.read_text(encoding="utf-8"))
        if prior["signature"] != signature:
            raise ValueError("检查点配置与当前环境不一致，拒绝混用结果")
    model_start = time.perf_counter()
    model = SentenceTransformer(MODEL, revision=REVISION, device=args.device)
    model.max_seq_length = 256
    with torch.inference_mode():
        qvec = model.encode([PREFIX + q["text"] for q in queries], batch_size=args.batch_size,
                            normalize_embeddings=True, convert_to_tensor=True, show_progress_bar=False)
    load_seconds = time.perf_counter() - model_start
    ranker = StreamingTopK(qvec, state=prior["rankings"] if prior else None)
    processed = prior["processed"] if prior else 0
    active_before = prior["active_seconds"] if prior else 0.0
    found_gold = set(prior["found_gold_ids"]) if prior else set()
    gold = {pid for query in queries for pid in query["positive_ids"]}
    cache = None if args.pilot else VectorCache(args.cache_dir, qvec.shape[1], processed, resume=prior is not None)
    if cache is not None and prior is None:
        args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        cache.sync()
        save_checkpoint(args.checkpoint, {"signature": signature, "processed": 0,
            "active_seconds": 0.0, "found_gold_ids": [], "rankings": ranker.state()})
    start = time.perf_counter()
    if args.device == "cuda":
        free, total = torch.cuda.mem_get_info()
        print(f"显卡剩余 {free / 1024**3:.2f}/{total / 1024**3:.2f} GiB", flush=True)
    with gzip.open(args.corpus, "rt", encoding="utf-8") as stream:
        if processed:
            print(f"恢复检查点：跳过已处理的 {processed} 条……", flush=True)
            for _ in range(processed):
                if not stream.readline():
                    raise ValueError("语料长度小于检查点位置")
            start = time.perf_counter()
        while True:
            remaining = args.pilot - processed if args.pilot else GROUP
            if args.pilot and remaining <= 0:
                break
            lines = list(itertools.islice(stream, min(GROUP, remaining) if args.pilot else GROUP))
            if not lines:
                break
            items = [line.rstrip("\r\n").split("\t", 1) for line in lines]
            if any(len(x) != 2 or not x[0] or not x[1] for x in items):
                raise ValueError(f"第 {processed} 条附近出现格式错误")
            ids, texts = [x[0] for x in items], [x[1] for x in items]
            found_gold.update(gold.intersection(ids))
            with torch.inference_mode():
                vectors = model.encode(texts, batch_size=args.batch_size, normalize_embeddings=True,
                                       convert_to_tensor=True, show_progress_bar=False)
                ranker.update(vectors, ids, processed)
                if cache is not None:
                    cache.append(ids, vectors)
            processed += len(items)
            active = active_before + time.perf_counter() - start
            if processed % CHECKPOINT_EVERY == 0:
                print(f"已处理 {processed} 段；平均 {processed / active:.1f} 段/秒", flush=True)
                if not args.pilot:
                    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
                    cache.sync()
                    save_checkpoint(args.checkpoint, {"signature": signature, "processed": processed,
                        "active_seconds": active, "found_gold_ids": sorted(found_gold), "rankings": ranker.state()})
            if args.device == "cuda":
                pace(processed, args.pause_seconds, temp_limit=args.temp_limit)
    active = active_before + time.perf_counter() - start
    resource = {"working_set": memory(), "cuda_peak_allocated_mib":
                round(torch.cuda.max_memory_allocated() / 1024**2, 2) if args.device == "cuda" else None}
    if args.pilot:
        print(json.dumps({"pilot_passages": processed, "active_seconds": active,
                          "passages_per_second": processed / active, "resources": resource}, ensure_ascii=False), flush=True)
        return
    cache.sync()
    save_checkpoint(args.checkpoint, {"signature": signature, "processed": processed,
        "active_seconds": active, "found_gold_ids": sorted(found_gold), "rankings": ranker.state()})
    cache.finish(processed)
    print("正在计算可复用向量缓存的 SHA256……", flush=True)
    cache_manifest = {"corpus_sha256": CORPUS_SHA, "model": MODEL, "model_revision": REVISION,
                      "max_seq_length": 256, "dimension": qvec.shape[1], "count": processed,
                      "normalized": True, "dtype": "little-endian float32", "id_format": "32-byte ASCII hex",
                      "vectors_file": cache.vectors_path.name, "vectors_sha256": sha256(cache.vectors_path),
                      "ids_file": cache.ids_path.name, "ids_sha256": sha256(cache.ids_path)}
    save_checkpoint(args.cache_dir / "manifest.json", cache_manifest)
    metadata = {**signature, "corpus_passages": processed, "active_seconds": active,
                "model_and_query_load_seconds_last_run": load_seconds, "resources_last_process": resource,
                "method": "full corpus exhaustive float32 inner product; normalized query and passage vectors; streaming top10",
                "label_note": "development split mirror; incomplete labels may leave unjudged relevant passages"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary = write_result(args.output, queries, ranker.results(), found_gold, metadata)
    print(json.dumps({"summary": summary, "metadata": metadata}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

