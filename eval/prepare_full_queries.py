"""固定 100 条未用于模型选型的问题，作为全语料评测集。"""
import gzip
import hashlib
import json
import random
import sys
from pathlib import Path

SEED = 20261104
COUNT = 100
SHA256 = "72fbf56f18e162bcec5f8c2c8940f2fe331e7e67336606a7b591047696281c32"


def main():
    if len(sys.argv) != 4:
        raise SystemExit("用法: python -m eval.prepare_full_queries 开发集.gz 小子集.json 输出.json")
    source, subset, output = map(Path, sys.argv[1:])
    if hashlib.sha256(source.read_bytes()).hexdigest() != SHA256:
        raise ValueError("开发集哈希不匹配")
    original = json.loads(subset.read_text(encoding="utf-8"))
    excluded = {q["id"] for q in original["queries"]}
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    eligible = [r for r in rows if r.get("positive_passages") and r.get("negative_passages")
                and str(r["query_id"]) not in excluded]
    selected = random.Random(SEED).sample(eligible, COUNT)
    queries = [{"id": str(r["query_id"]), "text": r["query"],
                "positive_ids": sorted({str(p["docid"]) for p in r["positive_passages"]})}
               for r in selected]
    old_passages = {p["id"] for p in original["passages"]}
    overlap = sum(bool(set(q["positive_ids"]) & old_passages) for q in queries)
    payload = {"seed": SEED, "source_sha256": SHA256, "selection": "100 eligible dev queries excluding previous 50; seed 20261104",
               "prior_subset_sha256": hashlib.sha256(subset.read_bytes()).hexdigest(),
               "eligible_after_exclusion": len(eligible), "queries": queries}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"固定保留集：{len(queries)} 题；与选型 50 题问题 ID 无重复")
    print(f"其中正例段落与原候选库有交集的问题：{overlap}；SHA256: {hashlib.sha256(text.encode('utf-8')).hexdigest()}")


if __name__ == "__main__":
    main()
