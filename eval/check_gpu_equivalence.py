"""检查 GPU 流式排名与固定小子集 CPU 评测逐题指标是否一致。"""
import json
import os
import sys
from pathlib import Path
os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parent.parent / "data" / "huggingface"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import torch
from sentence_transformers import SentenceTransformer
from eval.stream_rank import StreamingTopK
from eval.benchmark_dureader import evaluate_ranking

MODEL = "BAAI/bge-small-zh-v1.5"
REVISION = "7999e1d3359715c523056ef9478215996d62a620"
PREFIX = "为这个句子生成表示以用于检索相关文章："


def main():
    if len(sys.argv) != 4:
        raise SystemExit("用法: python -m eval.check_gpu_equivalence 子集.json CPU结果.json 输出.json")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    subset = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    baseline = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
    expected = {r["query_id"]: r for r in baseline["rows"]}
    model = SentenceTransformer(MODEL, revision=REVISION, device="cuda")
    model.max_seq_length = 256
    queries = subset["queries"]
    with torch.inference_mode():
        vectors = model.encode([PREFIX + q["text"] for q in queries], batch_size=16,
                               normalize_embeddings=True, convert_to_tensor=True, show_progress_bar=False)
        ranker = StreamingTopK(vectors)
        for offset in range(0, len(subset["passages"]), 256):
            batch = subset["passages"][offset:offset + 256]
            docs = model.encode([p["text"] for p in batch], batch_size=16,
                                normalize_embeddings=True, convert_to_tensor=True, show_progress_bar=False)
            ranker.update(docs, [p["id"] for p in batch], offset)
    differences = []
    keys = ("hit1", "hit5", "hit10", "recall10", "mrr10")
    for q, ranked in zip(queries, ranker.results()):
        actual = evaluate_ranking([x["id"] for x in ranked], set(q["positive_ids"]))
        original = expected[q["id"]]
        if any(abs(actual[k] - original[k]) > 1e-9 for k in keys):
            differences.append({"query_id": q["id"], "cpu": {k: original[k] for k in keys}, "gpu": actual})
    report = {"queries": len(queries), "matching_metrics": len(queries) - len(differences),
              "differences": differences, "note": "Compares per-query metrics, not complete ranking identity."}
    Path(sys.argv[3]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if differences:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
