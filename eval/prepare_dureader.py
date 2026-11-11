"""固定规则创建 DuReader Retrieval 开发集的小型共享候选库。"""
import gzip
import hashlib
import json
import random
import sys
from pathlib import Path

SEED = 20261103
COUNT = 50
NEGATIVES_PER_QUERY = 20
SOURCE_SHA256 = "72fbf56f18e162bcec5f8c2c8940f2fe331e7e67336606a7b591047696281c32"


def build(source):
    source = Path(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("源文件 SHA256 不一致，拒绝生成子集")
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        all_rows = [json.loads(line) for line in stream]
    eligible = [x for x in all_rows if x.get("positive_passages") and x.get("negative_passages")]
    if len({str(x["query_id"]) for x in all_rows}) != len(all_rows):
        raise ValueError("问题 ID 重复")
    selected = random.Random(SEED).sample(eligible, COUNT)
    passages, queries = {}, []
    for row in selected:
        positive = row["positive_passages"]
        negative = row["negative_passages"][:NEGATIVES_PER_QUERY]
        positives = {str(p["docid"]) for p in positive}
        if positives & {str(p["docid"]) for p in negative}:
            raise ValueError("同一问题的正负标签冲突")
        for item in positive + negative:
            key, text = str(item["docid"]), item["text"]
            if key in passages and passages[key] != text:
                raise ValueError(f"段落 ID 内容冲突：{key}")
            passages[key] = text
        queries.append({"id": str(row["query_id"]), "text": row["query"],
                        "positive_ids": sorted(positives)})
    ordered = [{"id": key, "text": passages[key]} for key in sorted(passages)]
    return {"schema": 1, "seed": SEED, "source_sha256": digest,
            "selection": f"{COUNT} queries with positive and negative; all positives + first {NEGATIVES_PER_QUERY} negatives per query; union deduplicated by docid",
            "eligible_queries": len(eligible), "queries": queries, "passages": ordered}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("用法: python -m eval.prepare_dureader 原始dev.jsonl.gz 子集.json")
    output = Path(sys.argv[2])
    output.parent.mkdir(parents=True, exist_ok=True)
    subset = build(sys.argv[1])
    output.write_text(json.dumps(subset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"固定子集：{len(subset['queries'])} 问题，{len(subset['passages'])} 段落，种子 {SEED}")


if __name__ == "__main__":
    main()
