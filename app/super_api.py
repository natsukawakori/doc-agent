"""本地 Super-agent 演示 API：模拟身份，不是用户认证。"""
import asyncio
import json
import queue
import threading
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from app.state import busy
from src.super_agent import simulation, orchestrator, tickets
from src.execution_control import ExecutionControl

router = APIRouter()
SIM_DB = simulation.DB
TICKET_DB = tickets.DB
PAGE = Path(__file__).resolve().parent/'static'/'super.html'


class PolicyRequest(BaseModel):
    mode: Literal['off','observe','auto']
    owner_allowed: bool = True
    visitor_allowed: bool = False
    bot_allowed: bool = True
    rule_enabled: bool = True


class TriggerRequest(BaseModel):
    role: Literal['owner','visitor','bot']
    kind: Literal['submit','inferred']
    text: str = Field(min_length=1, max_length=2000)
    questions: list[str] = Field(min_length=1, max_length=8)
    retrieval_level: int = Field(ge=0, le=3)
    plan: bool = False


class LevelRequest(BaseModel):
    level: int = Field(ge=0, le=3)


@router.post('/api/super/triggers/{trigger_id}/process')
def process_queued(trigger_id: str, body: LevelRequest):
    if not busy.acquire(blocking=False):
        raise HTTPException(409,'已有任务正在处理，请等待完成')
    try:
        decision = orchestrator.process(trigger_id,'observe',sim_db=SIM_DB,ticket_db=TICKET_DB)
        if decision.get('ticket_id'):
            current = tickets.get_ticket(decision['ticket_id'],path=TICKET_DB)
            if current['status'] in ('pending','paused','failed'):
                tickets.set_retrieval_level(decision['ticket_id'],body.level,path=TICKET_DB)
        return {'trigger_id':trigger_id,'decision':decision}
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    finally:
        busy.release()


class RunRequest(BaseModel):
    max_questions: int | None = Field(default=None, ge=1, le=8)
    retry_failed: bool = False


@router.get('/super')
def page():
    return FileResponse(PAGE)


@router.get('/api/super/settings')
def settings():
    identities = simulation.initialize(SIM_DB)
    with simulation.database(SIM_DB) as db:
        policy = orchestrator._policy(db,'observe')
        rows = {r['role']:r['id'] for r in db.execute('SELECT id,role FROM sim_identities')}
    return {'identities':identities, 'policy':{'mode':policy.mode,'version':policy.version,
            'owner_allowed':('cli',rows['owner']) in policy.allowed,
            'visitor_allowed':('cli',rows['visitor']) in policy.allowed,
            'bot_allowed':('cli',rows['bot']) in policy.bots,
            'rule_enabled':orchestrator.RULE in policy.enabled_rules}}


@router.post('/api/super/policy')
def set_policy(body: PolicyRequest):
    policy = orchestrator.configure(body.mode,owner_allowed=body.owner_allowed,
        visitor_allowed=body.visitor_allowed,bot_allowed=body.bot_allowed,
        rule_enabled=body.rule_enabled,sim_db=SIM_DB,ticket_db=TICKET_DB)
    return {'mode':policy.mode,'version':policy.version}


@router.post('/api/super/triggers')
def trigger(body: TriggerRequest):
    if not busy.acquire(blocking=False):
        raise HTTPException(409,'已有任务正在处理，请等待完成')
    try:
        event = simulation.emit(body.role,body.kind,body.text,body.questions,SIM_DB,plan_requested=body.plan)
        decision = orchestrator.process(event.id,'observe',sim_db=SIM_DB,ticket_db=TICKET_DB,plan=body.plan)
        if decision.get('ticket_id'):
            tickets.set_retrieval_level(decision['ticket_id'],body.retrieval_level,path=TICKET_DB)
        return {'trigger_id':event.id,'strength':event.strength,'decision':decision}
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    finally:
        busy.release()


@router.get('/api/super/tickets/{ticket_id}')
def get_ticket(ticket_id: str):
    try:
        return tickets.get_ticket(ticket_id,path=TICKET_DB)
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from exc


@router.post('/api/super/tickets/{ticket_id}/retrieval')
def set_level(ticket_id: str, body: LevelRequest):
    try:
        version = tickets.set_retrieval_level(ticket_id,body.level,path=TICKET_DB)
        return {'level':body.level,'version':version}
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc


@router.post('/api/super/tickets/{ticket_id}/pause')
def pause(ticket_id: str):
    try:
        tickets.request_pause(ticket_id,path=TICKET_DB)
        return {'message':'已请求在当前题结束后暂停'}
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc


@router.post('/api/super/tickets/{ticket_id}/run')
async def run_ticket(request: Request, ticket_id: str, body: RunRequest):
    if not busy.acquire(blocking=False):
        raise HTTPException(409,'已有任务正在处理，请等待完成')
    events = queue.Queue()
    connected = threading.Event()
    connected.set()
    def send(event):
        if connected.is_set(): events.put(event)
    try:
        control = ExecutionControl.from_env()
    except Exception:
        busy.release()
        raise
    def worker():
        try:
            result = orchestrator.run_approved(ticket_id,sim_db=SIM_DB,ticket_db=TICKET_DB,
                max_questions=body.max_questions,retry_failed=body.retry_failed,on_event=send,execution_control=control)
            send({'type':'done','result':result})
        except Exception as exc:
            send({'type':'error','message':f'{type(exc).__name__}: {exc}'})
        finally:
            busy.release()
    try:
        threading.Thread(target=worker,name='super-web',daemon=True).start()
    except Exception:
        busy.release()
        raise
    async def generate():
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.to_thread(events.get,True,10)
                except queue.Empty:
                    yield ': keep-alive\n\n'
                    continue
                yield 'data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
                if event['type'] in ('done','error'):
                    break
        finally:
            connected.clear()
    return StreamingResponse(generate(),media_type='text/event-stream',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
