"""Scan existing BGE vectors once for 100 fixed queries, without loading them in RAM."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["HF_HOME"] = str(ROOT / "data/huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from eval.full_guard import pace
from eval.process_memory import memory
from eval.full_stream import MODEL, REVISION, PREFIX

data = ROOT / "data/dureader"
cache = data / "bge_full_cache"
manifest = json.loads((cache / "manifest.json").read_text(encoding="utf8"))
raw = (data / "full_queries.json").read_bytes()
queries = json.loads(raw)["queries"]
frozen = json.loads((ROOT / "eval/full_queries_manifest.json").read_text(encoding="utf8"))
assert hashlib.sha256(raw).hexdigest() == frozen["queries_sha256"]
assert manifest["model"] == MODEL and manifest["model_revision"] == REVISION
assert (cache / "vectors.f32").stat().st_size == manifest["count"] * 512 * 4
assert (cache / "ids.bin").stat().st_size == manifest["count"] * 32
torch.set_num_threads(4)
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False
torch.cuda.reset_peak_memory_stats()
start = time.perf_counter()
model = SentenceTransformer(MODEL, revision=REVISION, device="cuda")
model.max_seq_length = 256
with torch.inference_mode():
    q = model.encode([PREFIX + x["text"] for x in queries], batch_size=16,
                     normalize_embeddings=True, convert_to_tensor=True)
    load_seconds = time.perf_counter() - start
    del model
    scores = torch.full((len(queries), 50), float("-inf"), device="cuda")
    positions = torch.zeros((len(queries), 50), dtype=torch.int64, device="cuda")
    offset = 0
    with (cache / "vectors.f32").open("rb") as vectors:
        while block := vectors.read(8192 * 512 * 4):
            array = np.frombuffer(block, dtype="<f4").reshape(-1, 512).copy()
            v = torch.from_numpy(array).to("cuda")
            local_scores, local_indices = torch.topk(q @ v.T, min(50, len(v)), dim=1)
            combined = torch.cat((scores, local_scores), dim=1)
            all_positions = torch.cat((positions, local_indices + offset), dim=1)
            scores, best = torch.topk(combined, 50, dim=1)
            positions = torch.gather(all_positions, 1, best)
            offset += len(v)
            if offset % (8192 * 64) == 0:
                print(f"scanned {offset}/{manifest['count']}", flush=True)
                pace(offset, 0, temp_limit=90)
    assert offset == manifest["count"]
    score_rows, index_rows = scores.cpu().tolist(), positions.cpu().tolist()
    rows = []
    with (cache / "ids.bin").open("rb") as ids:
        for query, score_row, index_row in zip(queries, score_rows, index_rows):
            candidates = []
            for score, index in zip(score_row, index_row):
                ids.seek(index * 32)
                candidates.append({"id": ids.read(32).decode("ascii"), "score": score})
            rows.append({"query_id": query["id"], "top50": candidates})
result = {"query_sha256": hashlib.sha256(raw).hexdigest(),
          "cache_vectors_sha256": manifest["vectors_sha256"], "count": offset,
          "load_seconds": load_seconds, "elapsed_seconds": time.perf_counter() - start,
          "memory": memory(), "cuda_peak_mib": round(torch.cuda.max_memory_allocated()/1024**2, 2),
          "rows": rows}
out = data / "dureader_top50.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
print(f"saved {out}", flush=True)
