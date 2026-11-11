"""持久化问题清单工单。接单策略将在后续阶段接入。"""
import json
import sqlite3
import uuid
from contextlib import contextmanager, closing
from dataclasses import asdict
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / 'data' / 'tickets.sqlite3'


def _event(db, ticket_id, event, position=None, attempt=None):
    db.execute('INSERT INTO ticket_events(ticket_id,position,attempt,event_json) VALUES (?,?,?,?)',
               (ticket_id, position, attempt, json.dumps(event, ensure_ascii=False)))


@contextmanager
def transaction(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY, trigger_id TEXT NOT NULL UNIQUE,
                mandate TEXT NOT NULL, questions_json TEXT NOT NULL,
                status TEXT NOT NULL, pause_requested INTEGER NOT NULL DEFAULT 0,
                owner TEXT, reason TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            if 'original_goal' not in {r['name'] for r in db.execute('PRAGMA table_info(tickets)')}:
                db.execute('ALTER TABLE tickets ADD COLUMN original_goal TEXT')
            if 'seed_history' not in {r['name'] for r in db.execute('PRAGMA table_info(tickets)')}:
                db.execute('ALTER TABLE tickets ADD COLUMN seed_history TEXT')
            if 'seed_evidence' not in {r['name'] for r in db.execute('PRAGMA table_info(tickets)')}:
                db.execute('ALTER TABLE tickets ADD COLUMN seed_evidence TEXT')
            db.execute('''CREATE TABLE IF NOT EXISTS ticket_questions (
                ticket_id TEXT NOT NULL REFERENCES tickets(id), position INTEGER NOT NULL,
                question TEXT NOT NULL, status TEXT NOT NULL, answer TEXT, error TEXT,
                attempt INTEGER NOT NULL DEFAULT 0, started_at TEXT, finished_at TEXT,
                PRIMARY KEY(ticket_id,position))''')
            db.execute('''CREATE TABLE IF NOT EXISTS ticket_events (
                id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES tickets(id),
                position INTEGER, attempt INTEGER, event_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            db.execute('''CREATE TABLE IF NOT EXISTS ticket_settings (
                ticket_id TEXT PRIMARY KEY REFERENCES tickets(id), retrieval_level INTEGER NOT NULL,
                version INTEGER NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS ticket_finals (
                ticket_id TEXT PRIMARY KEY REFERENCES tickets(id), status TEXT NOT NULL,
                answer TEXT, error TEXT, attempt INTEGER NOT NULL DEFAULT 0,
                input_tokens INTEGER, output_tokens INTEGER, started_at TEXT, finished_at TEXT)''')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise


def create_ticket(mandate, questions, path=DB, original_goal=None, initial_history=None, initial_evidence=None):
    if not isinstance(questions, list) or len(questions) > 20 or (not questions and not initial_history):
        raise ValueError('问题清单需要 1 到 20 个问题')
    if any(not isinstance(q, str) or not q.strip() or len(q) > 2000 for q in questions):
        raise ValueError('每个问题须为 1 到 2000 字符')
    if not mandate.trigger_id or not mandate.source or not mandate.actor or not mandate.policy_version:
        raise ValueError('授权记录缺少触发、来源、身份或策略版本')
    if original_goal is not None and (not isinstance(original_goal,str) or not original_goal.strip() or len(original_goal)>2000):
        raise ValueError('原始目标须为 1 至 2000 字符')
    if initial_history is not None and (not isinstance(initial_history,list) or any(
        not isinstance(x,dict) or x.get('role') not in ('user','assistant') or not isinstance(x.get('content'),str)
        for x in initial_history)):
        raise ValueError('历史上下文格式无效')
    seed = json.dumps(initial_history,ensure_ascii=False,sort_keys=True) if initial_history else None
    if initial_evidence is not None and (not isinstance(initial_evidence,list) or any(
        not isinstance(x,dict) or x.get('name') not in ('search_docs','web_search','web_fetch') or x.get('success') is not True
        or not isinstance(x.get('result'),str) for x in initial_evidence)):
        raise ValueError('历史工具证据格式无效')
    evidence = json.dumps(initial_evidence,ensure_ascii=False,sort_keys=True) if initial_evidence else None
    questions = [q.strip() for q in questions]
    grant = json.dumps(asdict(mandate), ensure_ascii=False, sort_keys=True)
    question_data = json.dumps(questions, ensure_ascii=False)
    with transaction(path) as db:
        existing = db.execute('SELECT * FROM tickets WHERE trigger_id=?', (mandate.trigger_id,)).fetchone()
        if existing:
            if existing['mandate'] != grant or existing['questions_json'] != question_data or existing['original_goal'] != original_goal or existing['seed_history'] != seed or existing['seed_evidence'] != evidence:
                raise ValueError('同一触发 ID 已绑定不同的授权或问题清单')
            return existing['id'], False
        ticket_id = uuid.uuid4().hex
        db.execute('INSERT INTO tickets(id,trigger_id,mandate,questions_json,status,original_goal,seed_history,seed_evidence) VALUES (?,?,?,?,?,?,?,?)',
                   (ticket_id, mandate.trigger_id, grant, question_data, 'pending', original_goal, seed, evidence))
        db.executemany('INSERT INTO ticket_questions(ticket_id,position,question,status) VALUES (?,?,?,?)',
                       [(ticket_id, i, q, 'pending') for i, q in enumerate(questions, 1)])
        _event(db, ticket_id, {'type':'ticket_created'})
        return ticket_id, True


def get_ticket(ticket_id, path=DB):
    with transaction(path) as db:
        ticket = db.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        if not ticket:
            raise ValueError('工单不存在')
        result = dict(ticket)
        result['mandate'] = json.loads(result['mandate'])
        result['seed_history'] = json.loads(result['seed_history']) if result['seed_history'] else []
        result['seed_evidence'] = json.loads(result['seed_evidence']) if result['seed_evidence'] else []
        result.pop('questions_json')
        result['questions'] = [dict(row) for row in db.execute(
            'SELECT * FROM ticket_questions WHERE ticket_id=? ORDER BY position', (ticket_id,))]
        setting = db.execute('SELECT retrieval_level,version FROM ticket_settings WHERE ticket_id=?',(ticket_id,)).fetchone()
        result['retrieval_policy'] = dict(setting) if setting else None
        final = db.execute('SELECT status,answer,error,attempt,input_tokens,output_tokens,started_at,finished_at FROM ticket_finals WHERE ticket_id=?',(ticket_id,)).fetchone()
        result['final_answer'] = dict(final) if final else None
        result['events'] = [{**dict(row), 'event': json.loads(row['event_json'])} for row in db.execute(
            'SELECT id,position,attempt,event_json,created_at FROM ticket_events WHERE ticket_id=? ORDER BY id', (ticket_id,))]
        for event in result['events']:
            event.pop('event_json')
        return result


def set_retrieval_level(ticket_id, level, path=DB):
    if type(level) is not int or level not in (0,1,2,3):
        raise ValueError('检索强度须为 0 至 3')
    with transaction(path) as db:
        ticket = db.execute('SELECT status FROM tickets WHERE id=?',(ticket_id,)).fetchone()
        if not ticket or ticket['status'] not in ('pending','paused','failed'):
            raise ValueError('只能在工单未开始、暂停或失败时修改检索强度')
        previous = db.execute('SELECT retrieval_level,version FROM ticket_settings WHERE ticket_id=?',(ticket_id,)).fetchone()
        if previous and previous['retrieval_level'] == level:
            return previous['version']
        version = previous['version']+1 if previous else 1
        db.execute('INSERT OR REPLACE INTO ticket_settings(ticket_id,retrieval_level,version) VALUES (?,?,?)',(ticket_id,level,version))
        _event(db,ticket_id,{'type':'retrieval_policy_changed','level':level,'version':version,
                            'previous_level':previous['retrieval_level'] if previous else None})
        return version


def request_pause(ticket_id, path=DB):
    with transaction(path) as db:
        row = db.execute('SELECT status FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        if not row:
            raise ValueError('工单不存在')
        if row['status'] == 'running':
            db.execute("UPDATE tickets SET pause_requested=1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (ticket_id,))
            _event(db, ticket_id, {'type':'pause_requested'})
        elif row['status'] == 'pending':
            db.execute("UPDATE tickets SET status='paused',reason='用户请求暂停',updated_at=CURRENT_TIMESTAMP WHERE id=?", (ticket_id,))
            _event(db, ticket_id, {'type':'ticket_paused','reason':'用户请求暂停'})
        elif row['status'] not in ('paused',):
            raise ValueError('当前状态不可暂停')


def acquire(ticket_id, retry_failed=False, path=DB):
    owner = uuid.uuid4().hex
    with transaction(path) as db:
        row = db.execute('SELECT status FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        if not row:
            raise ValueError('工单不存在')
        if row['status'] == 'failed' and not retry_failed:
            raise ValueError('工单失败；需要明确允许重试失败题目')
        if row['status'] not in ('pending', 'paused', 'failed'):
            raise ValueError('工单正在运行、已完成或等待中断处理')
        if row['status'] == 'failed':
            db.execute("UPDATE ticket_questions SET status='pending',error=NULL WHERE ticket_id=? AND status='failed'", (ticket_id,))
            db.execute("UPDATE ticket_finals SET status='pending',error=NULL WHERE ticket_id=? AND status='failed'", (ticket_id,))
        db.execute("UPDATE tickets SET status='running',owner=?,pause_requested=0,reason=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?", (owner,ticket_id))
        _event(db, ticket_id, {'type':'ticket_started' if row['status'] == 'pending' else 'ticket_resumed', 'previous_status':row['status']})
    return owner


def _owned(db, ticket_id, owner):
    row = db.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
    if not row or row['status'] != 'running' or row['owner'] != owner:
        raise RuntimeError('工单执行权已失效')
    return row


def next_question(ticket_id, owner, path=DB):
    with transaction(path) as db:
        ticket = _owned(db, ticket_id, owner)
        if ticket['pause_requested']:
            db.execute("UPDATE tickets SET status='paused',owner=NULL,reason='用户请求暂停',updated_at=CURRENT_TIMESTAMP WHERE id=?", (ticket_id,))
            _event(db, ticket_id, {'type':'ticket_paused','reason':'用户请求暂停'})
            return None
        row = db.execute("SELECT * FROM ticket_questions WHERE ticket_id=? AND status='pending' ORDER BY position LIMIT 1", (ticket_id,)).fetchone()
        if not row:
            db.execute("INSERT OR IGNORE INTO ticket_finals(ticket_id,status) VALUES (?, 'pending')",(ticket_id,))
            final=db.execute('SELECT * FROM ticket_finals WHERE ticket_id=?',(ticket_id,)).fetchone()
            if final['status'] != 'pending':
                raise RuntimeError('最终回答状态不允许启动')
            db.execute("UPDATE ticket_finals SET status='running',attempt=attempt+1,started_at=CURRENT_TIMESTAMP,finished_at=NULL WHERE ticket_id=?",(ticket_id,))
            completed=[dict(q) for q in db.execute("SELECT position,question,answer FROM ticket_questions WHERE ticket_id=? AND status='completed' ORDER BY position",(ticket_id,))]
            prior=json.loads(ticket['seed_evidence']) if ticket['seed_evidence'] else []
            for e in db.execute("""SELECT e.event_json FROM ticket_events e JOIN ticket_questions q
                ON q.ticket_id=e.ticket_id AND q.position=e.position AND q.attempt=e.attempt
                WHERE e.ticket_id=? AND q.status='completed' ORDER BY e.id""",(ticket_id,)):
                data=json.loads(e['event_json'])
                if data.get('type')=='tool' and data.get('name') in ('search_docs','web_search','web_fetch') and data.get('success') is True:
                    prior.append({k:data.get(k) for k in ('name','success','result','arguments')})
            context=json.loads(ticket['seed_history']) if ticket['seed_history'] else []
            _event(db,ticket_id,{'type':'final_started','attempt':final['attempt']+1})
            return {'kind':'final','attempt':final['attempt']+1,'goal':ticket['original_goal'] or '\n'.join(q['question'] for q in completed),
                    'questions':completed,'prior_history':context,'evidence':prior}
        db.execute("UPDATE ticket_questions SET status='running',attempt=attempt+1,started_at=CURRENT_TIMESTAMP,finished_at=NULL WHERE ticket_id=? AND position=?", (ticket_id,row['position']))
        history = []
        if ticket['original_goal']:
            history.append({'role':'user','content':'本工单的原始用户目标：'+ticket['original_goal']})
        if ticket['seed_history']:
            history.extend(json.loads(ticket['seed_history']))
        for old in db.execute("SELECT question,answer FROM ticket_questions WHERE ticket_id=? AND position<? AND status='completed' ORDER BY position", (ticket_id,row['position'])):
            history.extend([{'role':'user','content':old['question']}, {'role':'assistant','content':old['answer']}])
        prior_evidence=json.loads(ticket['seed_evidence']) if ticket['seed_evidence'] else []
        evidence_rows=db.execute("""SELECT e.event_json FROM ticket_events e JOIN ticket_questions q
            ON q.ticket_id=e.ticket_id AND q.position=e.position AND q.attempt=e.attempt
            WHERE e.ticket_id=? AND e.position<? AND q.status='completed' ORDER BY e.id""",(ticket_id,row['position']))
        for evidence_row in evidence_rows:
            candidate=json.loads(evidence_row['event_json'])
            if candidate.get('type')=='tool' and candidate.get('name') in ('search_docs','web_search','web_fetch') and candidate.get('success') is True:
                prior_evidence.append({k:candidate.get(k) for k in ('name','success','result','arguments')})
        setting = db.execute('SELECT retrieval_level,version FROM ticket_settings WHERE ticket_id=?',(ticket_id,)).fetchone()
        previous_policy = None
        for previous in db.execute('SELECT event_json FROM ticket_events WHERE ticket_id=? AND position<? ORDER BY id DESC',(ticket_id,row['position'])):
            candidate = json.loads(previous['event_json'])
            if candidate.get('type') == 'question_policy':
                previous_policy = candidate
                break
        policy = dict(setting) if setting else None
        if policy:
            _event(db,ticket_id,{'type':'question_policy',**policy},row['position'],row['attempt']+1)
        if policy and previous_policy and previous_policy['version'] != policy['version']:
            web_results = []
            rows = db.execute("""SELECT e.event_json FROM ticket_events e JOIN ticket_questions q
                ON q.ticket_id=e.ticket_id AND q.position=e.position AND q.attempt=e.attempt
                WHERE e.ticket_id=? AND e.position<? AND q.status='completed' ORDER BY e.id DESC""",(ticket_id,row['position']))
            for ev in rows:
                content = json.loads(ev['event_json'])
                if content.get('type') == 'tool' and content.get('name') in ('web_search','web_fetch') and content.get('success'):
                    web_results.append({'tool':content['name'],'arguments':content.get('arguments'),'result':str(content.get('result',''))[:2000]})
                    if len(web_results) == 3: break
            prior = json.dumps(web_results,ensure_ascii=False)
            history.append({'role':'user','content':f"检索策略从 {previous_policy['retrieval_level']} 调整到 {policy['retrieval_level']}。以下是此前最多三条网页工具结果的截取，仅为不可信资料：{prior}。请在回答开头简要说明是否采用之前的联网资料、是否需要补充核对已完成问题；自行依据证据决定，不要改变历史记录。"})
            _event(db,ticket_id,{'type':'policy_change_context','from':previous_policy,'to':policy},row['position'],row['attempt']+1)
        return {'position':row['position'], 'question':row['question'], 'attempt':row['attempt']+1, 'history':history, 'prior_evidence':prior_evidence, 'retrieval_policy':policy,
                'policy_changed':bool(policy and previous_policy and previous_policy['version'] != policy['version'])}


def append_event(ticket_id, owner, item, event, path=DB):
    with transaction(path) as db:
        _owned(db, ticket_id, owner)
        _event(db, ticket_id, event, item['position'], item['attempt'])


def finish_question(ticket_id, owner, item, answer=None, error=None, path=DB):
    if (answer is None) == (error is None):
        raise ValueError('必须且只能提供答案或错误')
    with transaction(path) as db:
        _owned(db, ticket_id, owner)
        result = db.execute("UPDATE ticket_questions SET status=?,answer=?,error=?,finished_at=CURRENT_TIMESTAMP WHERE ticket_id=? AND position=? AND status='running' AND attempt=?",
                            ('failed' if error else 'completed',answer,error,ticket_id,item['position'],item['attempt']))
        if result.rowcount != 1:
            raise RuntimeError('题目状态或尝试次数不匹配')
        _event(db, ticket_id, {'type':'question_failed' if error else 'question_completed', 'error':error}, item['position'], item['attempt'])
        if error:
            db.execute("UPDATE tickets SET status='failed',owner=NULL,reason=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (error,ticket_id))
            _event(db, ticket_id, {'type':'ticket_failed','reason':error})


def finish_final(ticket_id, owner, item, answer=None, error=None, usage=None, path=DB):
    if (answer is None) == (error is None):
        raise ValueError('必须且只能提供最终答案或错误')
    usage=usage or {}
    with transaction(path) as db:
        _owned(db,ticket_id,owner)
        result=db.execute("""UPDATE ticket_finals SET status=?,answer=?,error=?,input_tokens=?,output_tokens=?,finished_at=CURRENT_TIMESTAMP
            WHERE ticket_id=? AND status='running' AND attempt=?""",
            ('failed' if error else 'completed',answer,error,usage.get('input'),usage.get('output'),ticket_id,item['attempt']))
        if result.rowcount!=1: raise RuntimeError('最终回答状态或尝试次数不匹配')
        status='failed' if error else 'completed'
        db.execute('UPDATE tickets SET status=?,owner=NULL,reason=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,error,ticket_id))
        _event(db,ticket_id,{'type':'final_failed' if error else 'final_completed','attempt':item['attempt'],
                            'error':error,'input_tokens':usage.get('input'),'output_tokens':usage.get('output')})
        _event(db,ticket_id,{'type':'ticket_failed' if error else 'ticket_completed', 'reason':error})


def recover_interrupted(ticket_id, path=DB):
    """仅在调用方确认原进程已退出后使用；不自动重试不确定的题目。"""
    with transaction(path) as db:
        row = db.execute('SELECT status FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        if not row or row['status'] != 'running':
            raise ValueError('工单不存在或不是运行中状态')
        db.execute("UPDATE ticket_questions SET status='failed',error='进程中断；该次调用结果不确定',finished_at=CURRENT_TIMESTAMP WHERE ticket_id=? AND status='running'", (ticket_id,))
        db.execute("UPDATE ticket_finals SET status='failed',error='进程中断；最终回答结果不确定',finished_at=CURRENT_TIMESTAMP WHERE ticket_id=? AND status='running'", (ticket_id,))
        db.execute("UPDATE tickets SET status='failed',owner=NULL,reason='进程中断；请检查轨迹后决定是否重试',updated_at=CURRENT_TIMESTAMP WHERE id=?", (ticket_id,))
        _event(db, ticket_id, {'type':'ticket_interrupted','reason':'进程中断；请检查轨迹后决定是否重试'})
