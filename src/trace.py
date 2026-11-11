"""将 Agent 调用轨迹保存到本地 SQLite。"""
import json
import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "traces.sqlite3"


def save(question, calls, answer, seconds, tokens=None, error=None, model_steps=None, stop_reason=None):
    DB.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB)) as connection, connection:
        # 先取得写锁，确保并发进程不会同时检查并迁移同一旧表。
        connection.execute('BEGIN IMMEDIATE')
        connection.execute("""CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            question TEXT NOT NULL, tool_calls TEXT NOT NULL, answer TEXT,
            elapsed_seconds REAL NOT NULL, total_tokens INTEGER, error TEXT)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS tool_steps (
            run_id INTEGER NOT NULL, step INTEGER NOT NULL, tool_name TEXT,
            args_hash TEXT, result_chars INTEGER, latency_ms REAL,
            cache_hit INTEGER, success INTEGER, error TEXT,
            PRIMARY KEY (run_id, step))""")
        columns = {row[1] for row in connection.execute('PRAGMA table_info(tool_steps)')}
        if 'attempts' not in columns:
            connection.execute('ALTER TABLE tool_steps ADD COLUMN attempts INTEGER')
        connection.execute("""CREATE TABLE IF NOT EXISTS model_steps (
            run_id INTEGER NOT NULL, step INTEGER NOT NULL, latency_ms REAL,
            input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
            PRIMARY KEY (run_id, step))""")
        connection.execute('CREATE TABLE IF NOT EXISTS run_guards (run_id INTEGER PRIMARY KEY, reason TEXT NOT NULL)')
        cursor = connection.execute("""INSERT INTO runs
            (question, tool_calls, answer, elapsed_seconds, total_tokens, error)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (question, json.dumps(calls, ensure_ascii=False), answer, seconds, tokens, error))
        if stop_reason:
            connection.execute('INSERT INTO run_guards VALUES (?, ?)', (cursor.lastrowid, stop_reason))
        for step, model in enumerate(model_steps or [], 1):
            connection.execute('INSERT INTO model_steps VALUES (?, ?, ?, ?, ?, ?)',
                (cursor.lastrowid, step, model['seconds'] * 1000,
                 model.get('input_tokens'), model.get('output_tokens'), model.get('total_tokens')))
        for step, call in enumerate(calls, 1):
            args = str(call.get('arguments', ''))
            result = str(call.get('result', ''))
            duration = call.get('seconds')
            success = call.get('success')
            connection.execute("""INSERT INTO tool_steps
                (run_id, step, tool_name, args_hash, result_chars, latency_ms, cache_hit, success, error, attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cursor.lastrowid, step, call.get('name'), hashlib.sha256(args.encode('utf-8')).hexdigest(),
                 len(result), duration * 1000 if duration is not None else None,
                 int(bool(call.get('reused'))), int(success) if success is not None else None,
                 result[:500] if success is False else None, call.get('attempts')))
        return cursor.lastrowid


def save_memory(run_id, event):
    """把回答之后的摘要费用关联到产生该回答的运行。"""
    if not isinstance(run_id, int):
        raise ValueError('摘要需要有效的运行 ID')
    with closing(sqlite3.connect(DB)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        if not connection.execute('SELECT 1 FROM runs WHERE id=?', (run_id,)).fetchone():
            raise ValueError('运行记录不存在')
        connection.execute('''CREATE TABLE IF NOT EXISTS memory_steps (
            run_id INTEGER PRIMARY KEY, latency_ms REAL, before_chars INTEGER,
            after_chars INTEGER, input_tokens INTEGER, output_tokens INTEGER)''')
        connection.execute('INSERT INTO memory_steps VALUES (?, ?, ?, ?, ?, ?)',
            (run_id, event.get('seconds', 0) * 1000, event.get('before_chars'),
             event.get('after_chars'), event.get('summary_input_tokens'), event.get('summary_output_tokens')))
