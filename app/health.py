"""廉价的本机文件和配置检查，不加载检索模型，不调用远端服务。"""
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from src.llm import PROFILE

PROJECT = Path(__file__).resolve().parent.parent


def inspect_health(root=PROJECT):
    root = Path(root)
    index_files = ('data/dureader/bge_full_cache/manifest.json',
                   'data/dureader/bge_full_cache/ids.bin',
                   'data/dureader/bge_full_cache/vectors.f32',
                   'data/dureader/passage_lookup/manifest.json',
                   'data/dureader/passage_lookup/offsets.u64',
                   'data/dureader/passage_lookup/passages.tsv')
    present = all((root / name).is_file() for name in index_files)
    db = root / 'data/traces.sqlite3'
    db_ok = False
    if db.is_file():
        try:
            with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=1)) as con:
                con.execute('PRAGMA schema_version').fetchone()
                db_ok = True
        except sqlite3.Error:
            pass
    configured = all(os.getenv(key, '').strip() for key in ('LLM_BASE_URL','LLM_API_KEY','LLM_MODEL_ID'))
    return {'status':'ok' if present and db_ok and configured else 'degraded',
            'index_files_present':present, 'index_loaded':None, 'db_ok':db_ok,
            'llm_configured':bool(configured), 'llm_connection_checked':False,
            'profile':PROFILE, 'model':os.getenv('LLM_MODEL_ID', '').strip() or None}
