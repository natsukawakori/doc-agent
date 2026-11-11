"""独立 SQLite 决定记录，用触发 ID 防止重复接单。"""
import json
import hashlib
import sqlite3
from contextlib import closing


def record(path, trigger, decision):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS super_decisions (
            trigger_id TEXT PRIMARY KEY, source TEXT NOT NULL, actor TEXT NOT NULL,
            strength TEXT NOT NULL, input_hash TEXT NOT NULL, verdict TEXT NOT NULL, reason TEXT NOT NULL,
            policy_version TEXT NOT NULL, matched_rules TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        input_hash = hashlib.sha256(json.dumps([trigger.text, trigger.is_bot], ensure_ascii=False).encode('utf-8')).hexdigest()
        row = (trigger.id, trigger.source, trigger.actor, trigger.strength, input_hash, decision.verdict,
               decision.reason, decision.policy_version, json.dumps(decision.matched_rules, ensure_ascii=False))
        try:
            db.execute('INSERT INTO super_decisions (trigger_id,source,actor,strength,input_hash,verdict,reason,policy_version,matched_rules) VALUES (?,?,?,?,?,?,?,?,?)', row)
            return True
        except sqlite3.IntegrityError:
            existing = db.execute('SELECT trigger_id,source,actor,strength,input_hash,verdict,reason,policy_version,matched_rules FROM super_decisions WHERE trigger_id=?', (trigger.id,)).fetchone()
            if existing != row:
                raise ValueError('同一触发 ID 的内容或判定发生变化')
            return False


def recent_would_accept(path):
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT trigger_id,source,actor,reason,policy_version FROM super_decisions WHERE verdict='WOULD_ACCEPT' AND created_at >= datetime('now','-24 hours') ORDER BY created_at DESC").fetchall()
