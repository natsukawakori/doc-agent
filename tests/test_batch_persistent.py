import json
import unittest
from unittest.mock import patch
from src.agent import _run
from src.search_cache import prepare_batch


def call(i, query):
    return {'id': str(i), 'type': 'function', 'function': {'name': 'search_docs', 'arguments': json.dumps({'query': query})}}


class BatchPersistentTest(unittest.TestCase):
    def test_rejects_equivalent_queries_and_budget(self):
        calls = [call(1, 'a'), call(2, ' a ')]
        with patch('src.search_cache.key_for', side_effect=lambda query: query.strip()):
            self.assertIsNone(prepare_batch(calls, 4, {}))
        self.assertIsNone(prepare_batch(calls, 1, {}))

    def test_all_hit_preserves_order_and_skips_scan(self):
        calls = [call(1, 'a'), call(2, 'b')]
        replies = [{'content': None, 'tool_calls': calls}, {'content': '完成'}]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.dict('os.environ', {'DOC_AGENT_SEARCH_CACHE': '1'}), \
             patch('src.search_cache.prepare_batch', return_value=(['ka', 'kb'], ['A', 'B'])), \
             patch('src.agent.read_response', side_effect=replies), \
             patch('src.agent.run_batch') as scan:
            self.assertEqual(_run('问题', 8, state, []), '完成')
        scan.assert_not_called()
        self.assertEqual([x['result'] for x in state['calls']], ['A', 'B'])
        self.assertTrue(all(x['persistent_cache_hit'] and x['attempts'] == 0 for x in state['calls']))

    def test_partial_hit_scans_all_and_refreshes(self):
        calls = [call(1, 'a'), call(2, 'b')]
        replies = [{'content': None, 'tool_calls': calls}, {'content': '完成'}]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.dict('os.environ', {'DOC_AGENT_SEARCH_CACHE': '1'}), \
             patch('src.search_cache.prepare_batch', return_value=(['ka', 'kb'], ['old', None])), \
             patch('src.search_cache.put') as put, \
             patch('src.agent.read_response', side_effect=replies), \
             patch('src.agent.run_batch', return_value=(['new-a', 'new-b'], 1)) as scan:
            self.assertEqual(_run('问题', 8, state, []), '完成')
        scan.assert_called_once()
        self.assertEqual(put.call_count, 2)
        self.assertEqual([x['result'] for x in state['calls']], ['new-a', 'new-b'])
        self.assertFalse(any(x['persistent_cache_hit'] for x in state['calls']))
