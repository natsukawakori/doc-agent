import json
import os
import time
from pathlib import Path
from unittest.mock import patch
from src import agent

os.environ['DOC_AGENT_SEARCH_CACHE'] = '1'
query = 'native app是什么'
call = {'id': '1', 'type': 'function', 'function': {'name': 'search_docs', 'arguments': json.dumps({'query': query}, ensure_ascii=False)}}
results = []
for _ in range(2):
    state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
    replies = [{'content': None, 'tool_calls': [call]}, {'content': '完成'}]
    start = time.perf_counter()
    with patch.object(agent, 'read_response', side_effect=replies):
        agent._run(query, 2, state, [])
    item = state['calls'][0]
    results.append({'seconds': time.perf_counter()-start, 'success': item['success'],
                    'cache_hit': item['persistent_cache_hit'], 'result': item['result']})
result = {'first_seconds': results[0]['seconds'], 'second_seconds': results[1]['seconds'],
          'first_hit': results[0]['cache_hit'], 'second_hit': results[1]['cache_hit'],
          'both_success': all(x['success'] for x in results),
          'same_result': results[0]['result'] == results[1]['result']}
folder = Path('data/reports/cache_probe_20261106')
folder.mkdir(parents=True, exist_ok=False)
(folder/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
