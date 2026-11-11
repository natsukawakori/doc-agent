"""两次相同批量搜索对照：模型回复用桩，检索为真实本机运行。"""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch
from src.agent import _run

os.environ['DOC_AGENT_SEARCH_CACHE'] = '1'
queries = ['Native App 和操作系统有什么关系？', 'Web App 和浏览器有什么关系？']
calls = [{'id': str(i), 'type': 'function', 'function': {'name': 'search_docs',
         'arguments': json.dumps({'query': q}, ensure_ascii=False)}} for i, q in enumerate(queries)]


def main():
    rows = []
    for _ in range(2):
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        answers = [{'content': None, 'tool_calls': calls}, {'content': '完成'}]
        start = time.perf_counter()
        with patch('src.agent.read_response', side_effect=answers):
            _run('测试批量检索', 4, state, [])
        rows.append({'seconds': time.perf_counter()-start, 'calls': state['calls']})
    first, second = rows
    result = {'first_seconds': first['seconds'], 'second_seconds': second['seconds'],
              'first_hits': [x['persistent_cache_hit'] for x in first['calls']],
              'second_hits': [x['persistent_cache_hit'] for x in second['calls']],
              'all_success': all(x['success'] for r in rows for x in r['calls']),
              'same_results': [x['result'] for x in first['calls']] == [x['result'] for x in second['calls']]}
    target = Path('data/reports/batch_cache_probe_20261106.json')
    with target.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
