"""Resolve candidate IDs to passages and compare cached Top-10 with the original run."""
import gzip
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data" / "dureader"
HERE = Path(__file__).resolve().parent.parent / "data" / "dureader"
new = json.loads((HERE / "dureader_top50.json").read_text(encoding="utf8"))
old = json.loads((ROOT / "full_cached_result.json").read_text(encoding="utf8"))
queries = {x["id"]: x for x in json.loads((ROOT / "full_queries.json").read_text(encoding="utf8"))["queries"]}
old_rows = {x["query_id"]: x for x in old["rows"]}
ids = {item["id"] for row in new["rows"] for item in row["top50"]}
texts = {}
start = time.perf_counter()
with gzip.open(ROOT / "passage_collection.tsv.gz", "rt", encoding="utf8") as stream:
    for line in stream:
        pid, sep, text = line.rstrip("\r\n").partition("\t")
        if pid in ids:
            texts[pid] = text
        if len(texts) == len(ids):
            break
if set(texts) != ids:
    raise ValueError(f"missing {len(ids - set(texts))} candidate texts")
matches = 0
same_sets = 0
for row in new["rows"]:
    first = [v["id"] for v in row["top50"][:10]]
    previous = [v["id"] for v in old_rows[row["query_id"]]["top10"]]
    matches += first == previous
    same_sets += set(first) == set(previous)
    row["question"] = queries[row["query_id"]]["text"]
    row["gold_ids"] = queries[row["query_id"]]["positive_ids"]
    for item in row["top50"]:
        item["text"] = texts[item["id"]]
new["retrieval_seconds_with_text_scan"] = time.perf_counter() - start
new["old_top10_same_order"] = matches
new["old_top10_same_ids"] = same_sets
(HERE / "dureader_candidates50.json").write_text(json.dumps(new, ensure_ascii=False), encoding="utf8")
print(f"texts={len(texts)} old_top10_same_order={matches} same_ids={same_sets} seconds={new['retrieval_seconds_with_text_scan']:.1f}", flush=True)
