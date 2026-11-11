"""可选跨请求检索缓存；只持久化查询哈希和工具结果。"""
import hashlib
import json
from importlib.metadata import version
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data' / 'search_cache.sqlite3'
FILES = ('data/dureader/bge_full_cache/manifest.json', 'data/dureader/passage_lookup/manifest.json',
         'src/rag.py', 'src/faiss_scan.py', 'src/torch_scan.py', 'src/tools/search_docs.py')


def key_for(query, files=FILES):
    h = hashlib.sha256()
    dtype = os.getenv('DOC_AGENT_VECTOR_DTYPE', 'float32')
    h.update(json.dumps({'query': query.strip(), 'backend': os.getenv('DOC_AGENT_VECTOR_BACKEND', 'faiss'),
                         'dtype': dtype, 'sentence_transformers': version('sentence-transformers')},
                        sort_keys=True, ensure_ascii=False).encode('utf-8'))
    if dtype.lower().strip() == 'float16':
        files += ('data/dureader/bge_full_cache/manifest_f16.json',)
    for name in files:
        h.update(name.encode())
        h.update(hashlib.sha256((ROOT/name).read_bytes()).digest())
    return h.hexdigest()


def database(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=2)
    db.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, created REAL NOT NULL, value TEXT NOT NULL)')
    return db


def get(key, ttl=3600, path=DB, now=None):
    if ttl <= 0:
        return None
    now = time.time() if now is None else now
    with closing(database(path)) as db:
        row = db.execute('SELECT created, value FROM cache WHERE key=?', (key,)).fetchone()
    if row is None or not 0 <= now - row[0] < ttl:
        return None
    try:
        payload = json.loads(row[1])
        if not isinstance(payload, list) or any(
                not isinstance(item, dict) or not isinstance(item.get('text'), str)
                or not isinstance(item.get('source'), str)
                or not re.fullmatch(r'DuReader:[0-9a-f]{32}', item['source']) for item in payload):
            return None
    except (ValueError, TypeError):
        return None
    return row[1]


def put(key, value, path=DB, now=None):
    now = time.time() if now is None else now
    with closing(database(path)) as db, db:
        db.execute('INSERT OR REPLACE INTO cache (key, created, value) VALUES (?, ?, ?)', (key, now, value))


def execute_cached(name, arguments, execute):
    """缓存不可用时回退原工具；只缓存成功的单次文档检索。"""
    cache_key, cached = None, None
    if (name == 'search_docs' and set(arguments) == {'query'} and
            isinstance(arguments['query'], str) and arguments['query'].strip() and
            os.getenv('DOC_AGENT_SEARCH_CACHE', '0') == '1'):
        try:
            cache_key = key_for(arguments['query'])
            cached = get(cache_key)
        except Exception:
            cache_key = None
    if cached is not None:
        return cached, True, True
    result, success = execute(name, arguments)
    if cache_key and success:
        try:
            put(cache_key, result)
        except Exception:
            pass
    return result, success, False


def prepare_batch(calls, remaining, local_cache):
    """验证批量请求并返回缓存键及对应结果；不改变现有单轮复用规则。"""
    if not 2 <= len(calls) <= min(8, remaining):
        return None
    keys, local_keys = [], set()
    for call in calls:
        function = call['function']
        args = json.loads(function['arguments'])
        if (function['name'] != 'search_docs' or not isinstance(args, dict) or
                set(args) != {'query'} or not isinstance(args['query'], str) or not args['query'].strip()):
            return None
        local_key = json.dumps(args, ensure_ascii=False, sort_keys=True)
        key = key_for(args['query'])
        if local_key in local_cache or local_key in local_keys or key in keys:
            return None
        local_keys.add(local_key)
        keys.append(key)
    return keys, [get(key) for key in keys]
