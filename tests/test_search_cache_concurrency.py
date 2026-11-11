import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from src.search_cache import get, put


class CacheConcurrencyTest(unittest.TestCase):
    def test_concurrent_read_write_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)/'cache.sqlite3'
            def task(worker):
                for i in range(12):
                    key = f'{worker}-{i}'
                    value = '[{"source":"DuReader:' + f'{worker * 100 + i:032x}' + '","text":"ok"}]'
                    put(key, value, path=db)
                    if get(key, path=db) != value:
                        raise AssertionError('并发缓存读取结果不一致')
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(task, range(6)))
