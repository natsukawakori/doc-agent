import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from src.trace import save, save_memory
from fastapi.testclient import TestClient
from app.server import app
from app.state import sessions


class MemoryTraceTest(unittest.TestCase):
    def test_memory_cost_is_linked_to_exact_run_and_preserves_unknown_usage(self):
        with tempfile.TemporaryDirectory() as tmp, patch('src.trace.DB', Path(tmp) / 'trace.db'):
            first = save('同一问题', [], '一', 1, 10)
            second = save('同一问题', [], '二', 2, 20)
            save_memory(first, {'seconds': 1.5, 'before_chars': 100, 'after_chars': 40,
                                'summary_input_tokens': 12, 'summary_output_tokens': None})
            with closing(sqlite3.connect(Path(tmp) / 'trace.db')) as db:
                rows = db.execute('SELECT run_id, latency_ms, before_chars, after_chars, input_tokens, output_tokens FROM memory_steps').fetchall()
            self.assertEqual(rows, [(first, 1500, 100, 40, 12, None)])
            self.assertNotEqual(first, second)
            with self.assertRaises(ValueError):
                save_memory(9999, {})

    def test_web_associates_summary_with_run_not_question(self):
        def fake_run(question, history, observer, on_delta, execution_control=None):
            observer({'type': 'trace_saved', 'run_id': 42})
            return '回答'
        def fake_compress(history, observer):
            observer({'type': 'memory_compressed', 'summary_input_tokens': 9})
            return history
        with tempfile.TemporaryDirectory() as tmp, patch('app.stream.PROJECT', Path(tmp)), \
             patch('app.stream.run', side_effect=fake_run), patch('app.stream.compress', side_effect=fake_compress), \
             patch('app.stream.save_memory') as record, TestClient(app) as client:
            session = client.post('/api/session').json()['session_id']
            self.assertEqual(client.post('/chat', json={'session_id': session, 'question': '问题'}).status_code, 200)
            self.assertEqual(record.call_args.args[0], 42)
            self.assertEqual(record.call_args.args[1]['summary_input_tokens'], 9)
        sessions.clear()
