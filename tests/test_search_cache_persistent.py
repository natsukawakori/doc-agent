import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from src.search_cache import get, put
from src import agent


class SearchCacheTest(unittest.TestCase):
    def test_expiry_future_and_different_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)/'cache.db'
            put('key', '[]', path=db, now=100)
            self.assertEqual(get('key', ttl=10, path=db, now=109), '[]')
            self.assertIsNone(get('key', ttl=10, path=db, now=110))
            self.assertIsNone(get('key', ttl=10, path=db, now=99))
            self.assertIsNone(get('other', ttl=10, path=db, now=101))

    def test_corrupted_values_are_misses(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)/'cache.db'
            for value in ('not-json', '{}', '[{"source":"bad", "text":"x"}]', '[{"source":"DuReader:' + 'a'*32 + '", "text":null}]'):
                put('key', value, path=db, now=100)
                self.assertIsNone(get('key', ttl=10, path=db, now=101))
            good = '[{"source":"DuReader:' + 'a'*32 + '", "text":"ok"}]'
            put('key', good, path=db, now=100)
            self.assertEqual(get('key', ttl=10, path=db, now=101), good)

    def test_corrupt_row_triggers_real_fallback_and_replacement(self):
        call = {'id': '1', 'type': 'function', 'function': {'name': 'search_docs', 'arguments': '{"query":"q"}'}}
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)/'cache.db'
            put('key', 'broken', path=db)
            replies = [{'content': None, 'tool_calls': [call]}, {'content': 'done'}]
            state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
            with patch.dict('os.environ', {'DOC_AGENT_SEARCH_CACHE': '1'}), \
                 patch('src.search_cache.key_for', return_value='key'), \
                 patch('src.search_cache.get', side_effect=lambda k: get(k, path=db)), \
                 patch('src.search_cache.put', side_effect=lambda k, v: put(k, v, path=db)), \
                 patch.object(agent, 'read_response', side_effect=replies), \
                 patch.object(agent, 'run_tool_details', return_value=('[]', True)) as worker:
                self.assertEqual(agent._run('q', 2, state, []), 'done')
            worker.assert_called_once()
            self.assertEqual(get('key', path=db), '[]')
            self.assertFalse(state['calls'][0]['persistent_cache_hit'])

    def test_second_agent_run_uses_optional_cache(self):
        call = {'id': '1', 'type': 'function', 'function': {'name': 'search_docs', 'arguments': '{"query":"q"}'}}
        saved = {}
        def run_once():
            replies = [{'content': None, 'tool_calls': [call]}, {'content': 'done'}]
            state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
            with patch.object(agent, 'read_response', side_effect=replies):
                agent._run('q', 2, state, [])
            return state
        with patch.dict('os.environ', {'DOC_AGENT_SEARCH_CACHE': '1'}), \
             patch('src.search_cache.key_for', return_value='key'), \
             patch('src.search_cache.get', side_effect=lambda key: saved.get(key)), \
             patch('src.search_cache.put', side_effect=lambda key, value: saved.update({key: value})), \
             patch.object(agent, 'run_tool_details', return_value=('[]', True)) as tool:
            first, second = run_once(), run_once()
        self.assertEqual(tool.call_count, 1)
        self.assertFalse(first['calls'][0]['persistent_cache_hit'])
        self.assertTrue(second['calls'][0]['persistent_cache_hit'])
