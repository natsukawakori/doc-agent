import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from src import agent, trace


def call(i):
    return {'id': str(i), 'type': 'function', 'function': {'name': 'calc', 'arguments': '{"expression":"1+1"}'}}


class HarnessEdgeCases(unittest.TestCase):
    def test_mixed_batch_cannot_exceed_step_limit(self):
        calls = [call(1), call(2), call(3)]
        replies = [{'content': None, 'tool_calls': calls}, {'content': '结束'}]
        received = []
        def respond(messages, tools, *args):
            received.append(list(messages))
            return replies.pop(0)
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.object(agent, 'read_response', side_effect=respond), \
             patch.object(agent, 'run_tool_details', return_value=('2', True)) as worker:
            self.assertEqual(agent._run('q', 1, state, []), '结束')
        self.assertEqual(worker.call_count, 1)
        messages = [m for m in received[-1] if m.get('role') == 'tool']
        self.assertEqual([m['tool_call_id'] for m in messages], ['1', '2', '3'])
        self.assertEqual(json.loads(messages[1]['content'])['tool'], 'calc')
        self.assertEqual(state['stop_reason'], 'max_steps')

    def test_budget_is_cumulative_across_model_calls(self):
        replies = [{'content': None, 'tool_calls': [call(1)]}, {'content': None, 'tool_calls': [call(2)]}]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True, 'token_budget': 10}
        def respond(messages, tools, usage):
            usage['last'] = 6
            return replies.pop(0)
        with patch.object(agent, 'read_response', side_effect=respond), \
             patch.object(agent, 'run_tool_details', return_value=('2', True)) as worker:
            self.assertIn('预算', agent._run('q', 8, state, []))
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(state['tokens'], 12)
        self.assertEqual(state['stop_reason'], 'token_budget')

    def test_migrates_existing_tool_steps_without_losing_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'old.sqlite3'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE tool_steps (run_id INTEGER, step INTEGER, tool_name TEXT, args_hash TEXT, result_chars INTEGER, latency_ms REAL, cache_hit INTEGER, success INTEGER, error TEXT, PRIMARY KEY(run_id,step))')
                db.execute("INSERT INTO tool_steps (run_id,step,tool_name) VALUES (999,1,'old')")
            with patch.object(trace, 'DB', path):
                trace.save('q', [{'name':'calc', 'result':'2', 'success':True, 'attempts':1}], '2', .2)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT tool_name FROM tool_steps WHERE run_id=999').fetchone()[0], 'old')
                self.assertEqual(db.execute('SELECT attempts FROM tool_steps WHERE tool_name="calc"').fetchone()[0], 1)

    def test_actual_exclusive_db_lock_preserves_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'locked.sqlite3'
            lock = sqlite3.connect(path)
            try:
                lock.execute('CREATE TABLE marker (x INTEGER)')
                lock.execute('BEGIN EXCLUSIVE')
                real_connect = sqlite3.connect
                def quick_connect(*args, **kwargs):
                    kwargs['timeout'] = .05
                    return real_connect(*args, **kwargs)
                events = []
                with patch.object(trace, 'DB', path), patch.object(trace.sqlite3, 'connect', side_effect=quick_connect), \
                     patch.object(agent, '_run', return_value='答案'):
                    self.assertEqual(agent.run('q', observer=events.append), '答案')
                self.assertTrue(any('保存失败' in e.get('content', '') for e in events))
            finally:
                lock.rollback()
                lock.close()
