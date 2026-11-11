"""为全语料流式检索计算指标并输出可复核结果。"""
import json
from pathlib import Path


def write_result(path, queries, rankings, found_ids, metadata):
    rows = []
    for query, ranking in zip(queries, rankings):
        found = [item["id"] for item in ranking]
        relevant = set(query["positive_ids"])
        rank = next((i for i, docid in enumerate(found, 1) if docid in relevant), None)
        rows.append({"query_id": query["id"], "hit1": int(rank == 1),
                     "hit5": int(rank is not None and rank <= 5),
                     "hit10": int(rank is not None),
                     "recall10": len(set(found[:10]) & relevant) / len(relevant),
                     "mrr10": 1 / rank if rank else 0.0,
                     "gold_count": len(relevant), "gold_in_corpus": len(relevant & found_ids),
                     "top10": ranking})
    n = len(rows)
    summary = {"queries": n, **{key: sum(r[key] for r in rows) / n
                                    for key in ("hit1", "hit5", "hit10", "recall10", "mrr10")},
               "gold_labels": sum(r["gold_count"] for r in rows),
               "gold_labels_found_in_corpus": sum(r["gold_in_corpus"] for r in rows)}
    lines = ',\n'.join('    ' + json.dumps(row, ensure_ascii=False) for row in rows)
    text = ('{\n  "summary": ' + json.dumps(summary, ensure_ascii=False)
            + ',\n  "metadata": ' + json.dumps(metadata, ensure_ascii=False)
            + ',\n  "rows": [\n' + lines + '\n  ]\n}\n')
    Path(path).write_text(text, encoding="utf-8")
    return summary
