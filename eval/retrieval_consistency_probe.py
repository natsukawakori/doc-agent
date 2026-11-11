"""对两条开发查询比较真实批量和逐条检索，不调用聊天模型。"""
import json
import time
from pathlib import Path
from src.batch_dispatch import run_batch
from src.tool_dispatch import run_tool_details

QUERIES = ['Native App 和操作系统有什么关系？', 'Web App 和浏览器有什么关系？']


def main():
    output = Path('data/reports/retrieval_consistency_20261106.json')
    if output.exists():
        raise FileExistsError('报告已存在，不覆盖')
    calls = [{'id': str(i), 'type': 'function', 'function': {'name': 'search_docs',
             'arguments': json.dumps({'query': q}, ensure_ascii=False)}} for i, q in enumerate(QUERIES)]
    t = time.perf_counter()
    batch = run_batch(calls, 8, {})
    batch_seconds = time.perf_counter() - t
    if batch is None:
        raise RuntimeError('批量检索失败，不输出成功报告')
    batched = [json.loads(x) for x in batch[0]]
    singles, seconds = [], []
    for query in QUERIES:
        start = time.perf_counter()
        result, success = run_tool_details('search_docs', {'query': query})
        seconds.append(time.perf_counter()-start)
        if not success:
            raise RuntimeError('逐条检索失败：' + result[:300])
        singles.append(json.loads(result))
    checks = []
    for left, right in zip(batched, singles):
        max_diff = max((abs(a['rerank_score'] - b['rerank_score']) for a, b in zip(left, right)), default=0)
        checks.append({'same_count': len(left) == len(right),
                       'same_ids_in_order': [x['source'] for x in left] == [x['source'] for x in right],
                       'same_texts': [x['text'] for x in left] == [x['text'] for x in right],
                       'max_rerank_score_diff': max_diff})
    report = {'queries': QUERIES, 'batch_seconds': batch_seconds, 'single_seconds': seconds,
              'cases': checks, 'notes': '单次测量；不同运行的系统负载和缓存可能不同。'}
    with output.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
