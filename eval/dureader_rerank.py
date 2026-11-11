"""Offline cross-encoder scoring with one durable record per query."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent.parent / "data" / "dureader"
sys.path.insert(0, str(ROOT))
os.environ["HF_HOME"] = str(ROOT / "data/huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import torch
from sentence_transformers import CrossEncoder
from eval.full_guard import pace
from eval.process_memory import memory

MODEL = "BAAI/bge-reranker-base"
REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"
input_path = HERE / "dureader_candidates50.json"
raw = input_path.read_bytes()
rows = json.loads(raw)["rows"]
input_hash = hashlib.sha256(raw).hexdigest()
output = HERE / "dureader_rerank_scores.jsonl"
done = {}
if output.exists():
    for line in output.read_text(encoding="utf8").splitlines():
        record = json.loads(line)
        if record["input_sha256"] != input_hash or record["revision"] != REVISION:
            raise ValueError("existing scores do not match this input and model")
        done[record["query_id"]] = record
torch.set_num_threads(4)
torch.backends.cuda.matmul.allow_tf32 = False
start = time.perf_counter()
model = CrossEncoder(MODEL, revision=REVISION, max_length=384, device="cuda")
load_seconds = time.perf_counter() - start
print(f"loaded model in {load_seconds:.1f}s; resuming {len(done)}", flush=True)
with output.open("a", encoding="utf8") as f:
    for row in rows:
        if row["query_id"] in done:
            continue
        t = time.perf_counter()
        pairs = [(row["question"], x["text"]) for x in row["top50"]]
        scores = model.predict(pairs, batch_size=4, show_progress_bar=False)
        record = {"query_id": row["query_id"], "input_sha256": input_hash,
                  "revision": REVISION, "scores": [float(x) for x in scores],
                  "seconds": time.perf_counter() - t}
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
        done[row["query_id"]] = record
        if len(done) % 5 == 0:
            print(f"reranked {len(done)}/{len(rows)}; memory={memory()}", flush=True)
        pace(4096, 0, temp_limit=90)
print(json.dumps({"queries": len(done), "elapsed_seconds": time.perf_counter() - start,
                  "load_seconds": load_seconds, "memory": memory(),
                  "cuda_peak_mib": round(torch.cuda.max_memory_allocated()/1024**2, 2)}), flush=True)
