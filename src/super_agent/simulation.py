"""本地模拟来源：创建实验身份和待研判事件，不接单、不执行模型。"""
import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from .domain import Trigger

DB = Path(__file__).resolve().parents[2] / 'data' / 'super_simulation.sqlite3'
ROLES = {'owner': ('项目所有者', False), 'visitor': ('普通访客', False), 'bot': ('模拟机器人', True)}
EVENTS = {'submit': 'explicit', 'inferred': 'inferred'}


@contextmanager
def database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS sim_identities (
                id TEXT PRIMARY KEY, role TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
                is_bot INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            db.execute('''CREATE TABLE IF NOT EXISTS sim_triggers (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, identity_id TEXT NOT NULL REFERENCES sim_identities(id),
                role TEXT NOT NULL, event_kind TEXT NOT NULL, strength TEXT NOT NULL,
                is_bot INTEGER NOT NULL, text TEXT NOT NULL, questions_json TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            if 'plan_requested' not in {r['name'] for r in db.execute('PRAGMA table_info(sim_triggers)')}:
                db.execute('ALTER TABLE sim_triggers ADD COLUMN plan_requested INTEGER NOT NULL DEFAULT 0')
            if 'assessment_owner' not in {r['name'] for r in db.execute('PRAGMA table_info(sim_triggers)')}:
                db.execute('ALTER TABLE sim_triggers ADD COLUMN assessment_owner TEXT')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise


def initialize(path=DB):
    """为三种角色各建立一个稳定的模拟 ID；重复初始化不会改变已有 ID。"""
    with database(path) as db:
        for role, (label, is_bot) in ROLES.items():
            db.execute('INSERT OR IGNORE INTO sim_identities(id,role,label,is_bot) VALUES (?,?,?,?)',
                       (f'{role}-{uuid.uuid4().hex[:16]}', role, label, int(is_bot)))
        return [dict(row) for row in db.execute('SELECT id,role,label,is_bot,created_at FROM sim_identities ORDER BY role')]


def emit(role, event_kind, text, questions, path=DB, plan_requested=False):
    """通过预置角色和宿主事件类型构造 Trigger；文本不能定义身份或强度。"""
    if role not in ROLES or event_kind not in EVENTS:
        raise ValueError('不支持的模拟身份或事件类型')
    if role == 'bot' and event_kind == 'submit':
        raise ValueError('模拟机器人不能创建人类明确请求')
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError('事件描述须为 1 到 2000 个字符')
    if not isinstance(questions, list) or not 1 <= len(questions) <= 20 or any(
        not isinstance(q, str) or not q.strip() or len(q) > 2000 for q in questions
    ):
        raise ValueError('问题清单须包含 1 到 20 个非空字符串')
    initialize(path)
    with database(path) as db:
        identity = db.execute('SELECT * FROM sim_identities WHERE role=?', (role,)).fetchone()
        trigger = Trigger(uuid.uuid4().hex, 'cli', identity['id'], text.strip(), EVENTS[event_kind], bool(identity['is_bot']))
        db.execute('''INSERT INTO sim_triggers
            (id,source,identity_id,role,event_kind,strength,is_bot,text,questions_json,status,plan_requested)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (trigger.id, trigger.source, trigger.actor, role, event_kind, trigger.strength,
             int(trigger.is_bot), trigger.text, json.dumps([q.strip() for q in questions], ensure_ascii=False), 'pending',int(bool(plan_requested))))
        return trigger


def get_event(trigger_id, path=DB):
    with database(path) as db:
        row = db.execute('SELECT * FROM sim_triggers WHERE id=?', (trigger_id,)).fetchone()
        if row is None:
            raise ValueError('模拟事件不存在')
        data = dict(row)
        data['questions'] = json.loads(data.pop('questions_json'))
        data['is_bot'] = bool(data['is_bot'])
        return data


def to_trigger(event):
    """以已保存的宿主事件构造领域对象；不解析自然语言判断权限。"""
    if event['role'] not in ROLES or event['event_kind'] not in EVENTS:
        raise ValueError('模拟事件类型无效')
    if event['strength'] != EVENTS[event['event_kind']] or bool(event['is_bot']) != ROLES[event['role']][1]:
        raise ValueError('事件结构与来源角色不一致')
    if event['is_bot'] and event['strength'] != 'inferred':
        raise ValueError('模拟机器人不能形成明确的人类请求')
    return Trigger(event['id'], event['source'], event['identity_id'], event['text'], event['strength'], event['is_bot'])
