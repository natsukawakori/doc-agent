"""Re-run the actual first retrieval query of each accepted case without LLM calls."""
import hashlib
import json
import os
import time
from pathlib import Path

from src.rag import search_many

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "data/reports/m3_acceptance_dureader_m3_20261105"
output = FOLDER / "faiss_replay.json"
if output.exists():
    raise FileExistsError("replay output already exists; refusing overwrite")
if os.getenv("DOC_AGENT_VECTOR_BACKEND", "faiss").lower() != "faiss":
    raise ValueError("this comparison requires FAISS backend")
rows = [json.loads(line) for line in (FOLDER / "results.jsonl").read_text(encoding="utf8").splitlines()]
events = [json.loads(line) for line in (FOLDER / "events.jsonl").read_text(encoding="utf8").splitlines()]
queries = {x["id"]: x for x in json.loads((ROOT / "data/dureader/full_queries.json").read_text(encoding="utf8"))["queries"]}
if len(rows) != 20 or len({x["id"] for x in rows}) != 20:
    raise ValueError("acceptance must contain 20 completed distinct rows")
work = []
for row in rows:
    first = next((x for x in events if x["id"] == row["id"] and x["type"] == "tool"
                  and x.get("name") == "search_docs" and x.get("success")), None)
    if not first:
        raise ValueError(f"no successful retrieval: {row['id']}")
    work.append((row, json.loads(first["arguments"])["query"], json.loads(first["result"])))
results = []
started = time.perf_counter()
for offset in range(0, len(work), 4):
    block = work[offset:offset + 4]
    batch_start = time.perf_counter()
    new_rows = search_many([x[1] for x in block])
    for (old_row, query, old_results), new_results in zip(block, new_rows):
        old_ids = [v["source"] for v in old_results]
        new_ids = [v["source"] for v in new_results]
        gold = {"DuReader:" + x for x in queries[old_row["id"]]["positive_ids"]}
        results.append({"id": old_row["id"], "query": query, "old_ids": old_ids, "new_ids": new_ids,
                        "same_order": old_ids == new_ids,
                        "same_texts": [v["text"] for v in old_results] == [v["text"] for v in new_results],
                        "old_hit1": old_row["hit1"], "old_hit3": old_row["hit3"],
                        "new_hit1": bool(gold.intersection(new_ids[:1])),
                        "new_hit3": bool(gold.intersection(new_ids[:3]))})
    print(f"validated {len(results)}/20; batch {time.perf_counter()-batch_start:.2f}s", flush=True)
    partial = FOLDER / "faiss_replay.partial.json"
    partial.write_text(json.dumps({"rows": results}, ensure_ascii=False, indent=2), encoding="utf8")
summary = {"queries": len(results), "same_order": sum(x["same_order"] for x in results),
           "same_texts": sum(x["same_texts"] for x in results),
           "old_hit1": sum(x["old_hit1"] for x in results), "new_hit1": sum(x["new_hit1"] for x in results),
           "old_hit3": sum(x["old_hit3"] for x in results), "new_hit3": sum(x["new_hit3"] for x in results),
           "seconds": time.perf_counter()-started, "backend": "faiss",
           "rag_sha256": hashlib.sha256((ROOT / "src/rag.py").read_bytes()).hexdigest(),
           "faiss_scan_sha256": hashlib.sha256((ROOT / "src/faiss_scan.py").read_bytes()).hexdigest()}
output.write_text(json.dumps({"summary": summary, "rows": results}, ensure_ascii=False, indent=2), encoding="utf8")
print(json.dumps(summary, ensure_ascii=False), flush=True)
