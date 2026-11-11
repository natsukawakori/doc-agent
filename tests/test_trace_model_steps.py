import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from src.trace import save


class ModelTraceTest(unittest.TestCase):
    def test_keeps_unknown_tokens_and_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'trace.db'
            with patch('src.trace.DB', path):
                save('q', [], 'a', 1, model_steps=[{'seconds': .4, 'input_tokens': 20, 'output_tokens': None}], stop_reason='idle')
            with closing(sqlite3.connect(path)) as db:
                row = db.execute('select latency_ms,input_tokens,output_tokens,total_tokens from model_steps').fetchone()
                self.assertEqual(row, (400, 20, None, None))
                self.assertEqual(db.execute('select reason from run_guards').fetchone()[0], 'idle')
