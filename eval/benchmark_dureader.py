"""只用本地编码器与 FAISS，对固定 DuReader 子集执行检索基线。"""
import ctypes
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import faiss
from sentence_transformers import SentenceTransformer
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


def get_model():
    model = SentenceTransformer(MODEL, revision=MODEL_REVISION, device="cpu")
    model.max_seq_length = 256
    return model


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


def memory():
    if os.name != "nt":
        raise RuntimeError("当前内存测量实现仅支持 Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(MemoryCounters), ctypes.c_ulong]
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    mb = 1024 * 1024
    return {"working_set_mib": round(counters.WorkingSetSize / mb, 2),
            "peak_working_set_mib": round(counters.PeakWorkingSetSize / mb, 2),
            "private_bytes_mib": round(counters.PrivateUsage / mb, 2)}


def evaluate_ranking(found, relevant):
    if not relevant:
        raise ValueError("问题没有标注正例")
    rank = next((i for i, item in enumerate(found[:10], 1) if item in relevant), None)
    return {"hit1": int(rank == 1), "hit5": int(rank is not None and rank <= 5),
            "hit10": int(rank is not None), "recall10": len(set(found[:10]) & relevant) / len(relevant),
            "mrr10": 1 / rank if rank else 0.0}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("用法: python -m eval.benchmark_dureader 子集.json 结果.json")
    begin = time.perf_counter()
    raw = Path(sys.argv[1]).read_bytes()
    subset = json.loads(raw)
    queries, passages = subset["queries"], subset["passages"]
    if len(queries) != 50 or not passages:
        raise ValueError("子集不完整")
    mem_before = memory()
    start = time.perf_counter()
    model = get_model()
    load_seconds = time.perf_counter() - start
    mem_model = memory()
    index = faiss.IndexFlatIP(model.get_sentence_embedding_dimension())
    start = time.perf_counter()
    for offset in range(0, len(passages), 32):
        batch = passages[offset:offset + 32]
        embeddings = model.encode([x["text"] for x in batch], normalize_embeddings=True,
                                  convert_to_numpy=True, show_progress_bar=False)
        index.add(embeddings.astype("float32"))
        if (offset // 32) % 10 == 0:
            print(f"索引 {min(offset + 32, len(passages))}/{len(passages)}", flush=True)
    index_seconds = time.perf_counter() - start
    mem_index = memory()
    ids = [item["id"] for item in passages]
    model.encode([queries[0]["text"]], normalize_embeddings=True, convert_to_numpy=True)
    rows = []
    for query in queries:
        started = time.perf_counter()
        embedding = model.encode([query["text"]], normalize_embeddings=True, convert_to_numpy=True)
        encode_ms = (time.perf_counter() - started) * 1000
        search_start = time.perf_counter()
        _, offsets = index.search(embedding.astype("float32"), 10)
        search_ms = (time.perf_counter() - search_start) * 1000
        found = [ids[n] for n in offsets[0] if n >= 0]
        relevant = set(query["positive_ids"])
        rows.append({"query_id": query["id"], **evaluate_ranking(found, relevant),
                     "encode_ms": encode_ms, "faiss_ms": search_ms,
                     "total_ms": (time.perf_counter() - started) * 1000})
    durations = sorted(row["total_ms"] for row in rows)
    n = len(rows)
    summary = {"queries": n, "passages": len(passages),
               **{key: sum(row[key] for row in rows) / n for key in ("hit1", "hit5", "hit10", "recall10", "mrr10")},
               "latency_mean_ms": statistics.mean(durations),
               "latency_median_ms": statistics.median(durations),
               "latency_p95_ms": durations[math.ceil(n * .95) - 1],
               "query_total_seconds": sum(durations) / 1000,
               "model_load_seconds": load_seconds, "index_build_seconds": index_seconds,
               "process_elapsed_seconds": time.perf_counter() - begin,
               "memory_before_model": mem_before, "memory_after_model": mem_model,
               "memory_after_index": mem_index, "memory_after_queries": memory()}
    metadata = {"dataset": "DuReader Retrieval dev, third-party mirror", "seed": subset["seed"],
                "source_sha256": subset["source_sha256"], "subset_sha256": hashlib.sha256(raw).hexdigest(),
                "selection": subset["selection"], "model": MODEL, "model_revision": MODEL_REVISION,
                "model_max_seq_length": model.max_seq_length, "candidate_unit": "original passage, truncated by model tokenizer if needed",
                "faiss_index": "IndexFlatIP, normalized embeddings", "python": platform.python_version(),
                "platform": platform.platform(), "logical_cpus": os.cpu_count(),
                "memory_scope": "current Python process, Windows working set; excludes other processes", "warmup_queries": 1,
                "latency_scope": "warm per-query embedding + FAISS + result matching, sequential; excludes index build and model load"}
    output = {"summary": summary, "metadata": metadata, "rows": rows}
    path = Path(sys.argv[2])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
