"""Convert verified document vectors to a reversible, separate float16 cache."""
import hashlib
import json
import os
import time
from pathlib import Path
import numpy as np

base = Path(__file__).resolve().parent.parent / "data" / "dureader" / "bge_full_cache"
meta = json.loads((base / "manifest.json").read_text(encoding="utf8"))
source = base / meta["vectors_file"]
partial = base / "vectors.f16.partial"
target = base / "vectors.f16"
output = base / "manifest_f16.json"
if any(p.exists() for p in (partial, target, output)):
    raise FileExistsError("float16 cache already exists; refusing overwrite")
if source.stat().st_size != meta["count"] * meta["dimension"] * 4:
    raise ValueError("source vector length mismatch")
start = time.perf_counter()
source_hash, target_hash = hashlib.sha256(), hashlib.sha256()
written = 0
with source.open("rb") as src, partial.open("xb") as dest:
    while block := src.read(8192 * 512 * 4):
        source_hash.update(block)
        converted = np.frombuffer(block, dtype="<f4").astype("<f2").tobytes()
        target_hash.update(converted)
        dest.write(converted)
        written += len(converted)
        if written % (1024**3) == 0:
            print(f"converted {written/1024**3:.1f} GiB", flush=True)
    dest.flush()
    os.fsync(dest.fileno())
if source_hash.hexdigest() != meta["vectors_sha256"] or written != meta["count"] * meta["dimension"] * 2:
    raise ValueError("source hash or derived length mismatch; partial retained")
os.replace(partial, target)
record = {"source_sha256": source_hash.hexdigest(), "vectors_sha256": target_hash.hexdigest(),
          "corpus_sha256": meta["corpus_sha256"], "ids_sha256": meta["ids_sha256"],
          "model": meta["model"], "model_revision": meta["model_revision"],
          "max_seq_length": meta["max_seq_length"], "dimension": meta["dimension"],
          "count": meta["count"], "dtype": "little-endian float16", "vectors_file": target.name,
          "seconds": time.perf_counter()-start}
temp = base / "manifest_f16.json.partial"
temp.write_text(json.dumps(record, indent=2), encoding="utf8")
os.replace(temp, output)
print(json.dumps(record), flush=True)
