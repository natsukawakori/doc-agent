import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import agent, search_cache


def call(identifier, query):
    return {'id': str(identifier), 'type': 'function', 'function': {'name': 'search_docs',
            'arguments': json.dumps({'query': query})}}


class IncrementalOfflineTest(unittest.TestCase):
    def test_fingerprint_changes_on_dependency_and_backend(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'manifest').write_text('v1', encoding='utf-8')
            with patch.object(search_cache, 'ROOT', root), patch.object(search_cache, 'version', return_value='1'), \
                 patch.dict('os.environ', {'DOC_AGENT_VECTOR_BACKEND': 'faiss', 'DOC_AGENT_VECTOR_DTYPE': 'float32'}):
                first = search_cache.key_for(' q ', files=('manifest',))
                self.assertEqual(first, search_cache.key_for('q', files=('manifest',)))
                (root/'manifest').write_text('v2', encoding='utf-8')
                second = search_cache.key_for('q', files=('manifest',))
                self.assertNotEqual(first, second)
                with patch.dict('os.environ', {'DOC_AGENT_VECTOR_BACKEND': 'torch'}):
                    self.assertNotEqual(second, search_cache.key_for('q', files=('manifest',)))

    def test_corrupt_cache_falls_back_to_worker(self):
        calls = [call(1, 'q')]
        replies = [{'content': None, 'tool_calls': calls}, {'content': 'done'}]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.dict('os.environ', {'DOC_AGENT_SEARCH_CACHE': '1'}), \
             patch('src.search_cache.key_for', return_value='k'), \
             patch('src.search_cache.get', side_effect=RuntimeError('corrupt')), \
             patch.object(agent, 'read_response', side_effect=replies), \
             patch.object(agent, 'run_tool_details', return_value=('[]', True)) as tool:
            self.assertEqual(agent._run('test', 2, state, []), 'done')
        tool.assert_called_once()
        self.assertFalse(state['calls'][0]['persistent_cache_hit'])

    def test_batch_cache_error_falls_back_to_batch_worker(self):
        calls = [call(1, 'a'), call(2, 'b')]
        replies = [{'content': None, 'tool_calls': calls}, {'content': 'done'}]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.dict('os.environ', {'DOC_AGENT_SEARCH_CACHE': '1'}), \
             patch('src.search_cache.prepare_batch', side_effect=OSError('unavailable')), \
             patch.object(agent, 'read_response', side_effect=replies), \
             patch.object(agent, 'run_batch', return_value=(['A', 'B'], 1)) as scan:
            self.assertEqual(agent._run('test', 8, state, []), 'done')
        scan.assert_called_once()
        self.assertEqual([x['result'] for x in state['calls']], ['A', 'B'])

    def test_exhausted_budget_stops_before_tool(self):
        calls = [call(1, 'q')]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True, 'token_budget': 10}
        def response(messages, tools, usage):
            usage['last'] = 10
            return {'content': None, 'tool_calls': calls}
        with patch.object(agent, 'read_response', side_effect=response), \
             patch.object(agent, 'run_tool_details') as tool:
            self.assertIn('预算', agent._run('test', 8, state, []))
        tool.assert_not_called()
        self.assertEqual(state['stop_reason'], 'token_budget')

    def test_success_resets_consecutive_error_streak(self):
        calls = [call(i, q) for i, q in enumerate(('a','b','c','d','e'))]
        replies = [{'content': None, 'tool_calls': [c]} for c in calls] + [{'content': 'done'}]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.object(agent, 'read_response', side_effect=replies), \
             patch.object(agent, 'run_tool_details', side_effect=[('err', False), ('err', False), ('ok', True), ('err', False), ('err', False)]):
            self.assertEqual(agent._run('test', 8, state, []), 'done')
        self.assertNotIn('stop_reason', state)
