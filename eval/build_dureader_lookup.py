"""Build an ordinal-to-text disk lookup, checking every cached passage ID."""
import gzip
import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.process_memory import memory

data = ROOT / "data/dureader"
cache = data / "bge_full_cache"
folder = data / "passage_lookup"
manifest = json.loads((cache / "manifest.json").read_text(encoding="utf8"))
source = data / "passage_collection.tsv.gz"
folder.mkdir(exist_ok=True)
for name in ("passages.tsv", "offsets.u64", "manifest.json", "passages.tsv.partial", "offsets.u64.partial"):
    if (folder / name).exists():
        raise FileExistsError(f"refusing to overwrite {folder / name}")
start = time.perf_counter()
digest = hashlib.sha256()
with source.open("rb") as f:
    while block := f.read(8 * 1024 * 1024):
        digest.update(block)
if digest.hexdigest() != manifest["corpus_sha256"]:
    raise ValueError("corpus hash mismatch")
count = 0
offset = 0
with gzip.open(source, "rb") as corpus, (cache / "ids.bin").open("rb") as ids, \
        (folder / "passages.tsv.partial").open("xb", buffering=8*1024*1024) as text, \
        (folder / "offsets.u64.partial").open("xb", buffering=1024*1024) as offsets:
    for line in corpus:
        expected_id = ids.read(32)
        if len(expected_id) != 32 or len(line) < 34 or line[:32] != expected_id or line[32:33] != b"\t":
            raise ValueError(f"corpus/cache ID mismatch at ordinal {count}")
        offsets.write(struct.pack("<Q", offset))
        text.write(line)
        offset += len(line)
        count += 1
        if count % 1_000_000 == 0:
            print(f"indexed {count}/{manifest['count']} passages; {offset/1024**3:.2f} GiB", flush=True)
    if count != manifest["count"] or ids.read(1):
        raise ValueError("corpus/cache count mismatch")
    for f in (text, offsets):
        f.flush()
        os.fsync(f.fileno())
os.replace(folder / "passages.tsv.partial", folder / "passages.tsv")
os.replace(folder / "offsets.u64.partial", folder / "offsets.u64")
result = {"version": 1, "count": count, "corpus_sha256": digest.hexdigest(),
          "ids_sha256": manifest["ids_sha256"], "text_bytes": offset,
          "offset_bytes": count * 8, "build_seconds": time.perf_counter() - start,
          "build_process_memory": memory()}
tmp = folder / "manifest.json.partial"
tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
os.replace(tmp, folder / "manifest.json")
print(json.dumps(result, ensure_ascii=False), flush=True)
