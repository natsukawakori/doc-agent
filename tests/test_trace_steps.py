import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from src.trace import save


class StepTraceTest(unittest.TestCase):
    def test_step_is_linked_and_arguments_hashed(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)/'trace.db'
            with patch('src.trace.DB', db):
                save('q', [{'name': 'calc', 'arguments': 'secret', 'result': '2',
                            'seconds': .1, 'success': True, 'reused': True}], '2', .2)
            with closing(sqlite3.connect(db)) as conn:
                row = conn.execute('SELECT run_id, step, tool_name, args_hash, latency_ms, cache_hit FROM tool_steps').fetchone()
                self.assertEqual(conn.execute('SELECT id FROM runs').fetchone()[0], row[0])
            self.assertEqual(row[1:3], (1, 'calc'))
            self.assertNotEqual(row[3], 'secret')
            self.assertEqual(row[4:], (100.0, 1))
