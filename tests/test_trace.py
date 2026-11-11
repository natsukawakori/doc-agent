import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.trace import save


class TraceTest(unittest.TestCase):
    def test_records_error_and_unknown_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'traces.sqlite3'
            with patch('src.trace.DB', db_path):
                save('问题', [{'name': 'calc', 'success': False}], None, 1.25, None, '失败')
            with closing(sqlite3.connect(db_path)) as db:
                question, calls, seconds, tokens, error = db.execute(
                    'SELECT question, tool_calls, elapsed_seconds, total_tokens, error FROM runs').fetchone()
            self.assertEqual(question, '问题')
            self.assertFalse(json.loads(calls)[0]['success'])
            self.assertEqual(seconds, 1.25)
            self.assertIsNone(tokens)
            self.assertEqual(error, '失败')


if __name__ == '__main__':
    unittest.main()
