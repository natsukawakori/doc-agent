"""Compare official-style metrics and deduplication for the same cached candidates."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "data" / "dureader"
data = json.loads((HERE / "dureader_candidates50.json").read_text(encoding="utf8"))
records = [json.loads(line) for line in (HERE / "dureader_rerank_scores.jsonl").read_text(encoding="utf8").splitlines()]
scores = {r["query_id"]: r for r in records}
assert len(scores) == len(data["rows"]) == 100


def signature(text):
    text = re.sub(r"\s+", "", text).lower()[:2000]
    return {text[i:i + 3] for i in range(max(1, len(text) - 2))} if text else set()


def deduplicate(items, near=False):
    kept, keys = [], []
    for item in items:
        normalized = re.sub(r"\s+", "", item["text"]).lower()
        key = signature(item["text"]) if near else normalized
        duplicate = False
        for old in keys:
            if near:
                duplicate = bool(key and old and len(key & old) / len(key | old) >= 0.90)
            else:
                duplicate = key == old
            if duplicate:
                break
        if not duplicate:
            kept.append(item)
            keys.append(key)
    return kept


def metrics(rows):
    total = len(rows)
    output = {}
    for k in (1, 5, 10, 50):
        output[f"hit{k}"] = sum(any(x["id"] in gold for x in ranking[:k]) for ranking, gold in rows) / total
    output["mrr10"] = sum(next((1/i for i, x in enumerate(ranking[:10], 1) if x["id"] in gold), 0)
                          for ranking, gold in rows) / total
    output["macro_recall10"] = sum(len({x["id"] for x in ranking[:10]} & gold) / len(gold)
                                   for ranking, gold in rows) / total
    return output


groups = {k: [] for k in ("dense", "dense_exact_dedup", "dense_near_dedup", "rerank", "rerank_near_dedup")}
details = []
for row in data["rows"]:
    raw = row["top50"]
    record = scores[row["query_id"]]
    assert len(raw) == len(record["scores"]) == 50
    ranked = [dict(item, rerank_score=float(score)) for item, score in zip(raw, record["scores"])]
    ranked.sort(key=lambda x: x["rerank_score"], reverse=True)
    orders = {"dense": raw, "dense_exact_dedup": deduplicate(raw),
              "dense_near_dedup": deduplicate(raw, True), "rerank": ranked,
              "rerank_near_dedup": deduplicate(ranked, True)}
    gold = set(row["gold_ids"])
    for name, ranking in orders.items():
        groups[name].append((ranking, gold))
    ranks = {name: next((i for i, x in enumerate(ranking, 1) if x["id"] in gold), None)
             for name, ranking in orders.items()}
    details.append({"query_id": row["query_id"], "question": row["question"], "first_gold_rank": ranks,
                    "dense_near_removed": 50-len(orders["dense_near_dedup"]),
                    "rerank_near_removed": 50-len(orders["rerank_near_dedup"]),
                    "top3_ids": {name: [v["id"] for v in ranking[:3]] for name, ranking in orders.items()}})
report = {"query_count": len(details), "metrics": {name: metrics(rows) for name, rows in groups.items()},
          "rerank_inference_seconds_sum": sum(r["seconds"] for r in records),
          "dense_seconds": data["elapsed_seconds"], "text_lookup_seconds": data["retrieval_seconds_with_text_scan"],
          "dedup_near_threshold": 0.9, "details": details}
(HERE / "dureader_comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
print(json.dumps({k:v for k,v in report.items() if k != "details"}, ensure_ascii=False, indent=2))
