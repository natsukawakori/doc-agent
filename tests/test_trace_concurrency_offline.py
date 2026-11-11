import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from src import trace


class TraceConcurrencyTest(unittest.TestCase):
    def test_parallel_saves_during_old_schema_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'traces.sqlite3'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE tool_steps (run_id INTEGER, step INTEGER, tool_name TEXT, args_hash TEXT, result_chars INTEGER, latency_ms REAL, cache_hit INTEGER, success INTEGER, error TEXT, PRIMARY KEY(run_id,step))')
            def save(i):
                trace.save('q', [{'name':'calc', 'result':'2', 'success':True, 'attempts':1}], '2', .1)
            with patch.object(trace, 'DB', path), ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(save, range(16)))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0], 16)
                self.assertEqual(db.execute('SELECT count(*) FROM tool_steps WHERE attempts=1').fetchone()[0], 16)
