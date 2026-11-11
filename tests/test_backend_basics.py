import asyncio
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import health, server, stream, super_api
from app.state import busy, sessions
from src import agent
from src.execution_control import ExecutionControl, ExecutionStopped
from src.super_agent import tickets
from src.super_agent.domain import Mandate
from src.super_agent.ticket_runner import run_ticket


class BackendBasicsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_health_is_safe_and_does_not_load_models(self):
        env={'LLM_API_KEY':'secret-for-test','LLM_BASE_URL':'https://example.test','LLM_MODEL_ID':'test-model'}
        with patch.dict(os.environ,env,clear=True):
            result=health.inspect_health(self.root)
        self.assertEqual(result['status'],'degraded')
        self.assertFalse(result['index_files_present'])
        self.assertFalse(result['db_ok'])
        self.assertIsNone(result['index_loaded'])
        self.assertNotIn('secret-for-test',json.dumps(result))
        self.assertFalse(result['llm_connection_checked'])
        with TestClient(server.app) as client:
            self.assertEqual(client.get('/healthz').status_code,200)
        for name in ('data/dureader/bge_full_cache/manifest.json','data/dureader/bge_full_cache/ids.bin',
                     'data/dureader/bge_full_cache/vectors.f32','data/dureader/passage_lookup/manifest.json',
                     'data/dureader/passage_lookup/offsets.u64','data/dureader/passage_lookup/passages.tsv'):
            path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.touch()
        db=self.root/'data/traces.sqlite3'
        with closing(sqlite3.connect(db)) as con: con.execute('CREATE TABLE example(id INTEGER)')
        with patch.dict(os.environ,env,clear=True):
            self.assertEqual(health.inspect_health(self.root)['status'],'ok')
            db.write_bytes(b'not a database')
            self.assertFalse(health.inspect_health(self.root)['db_ok'])

    def test_deadline_and_cancel_are_checked_before_model(self):
        clock=[0.0]
        control=ExecutionControl(1,clock=lambda:clock[0])
        clock[0]=2
        with self.assertRaises(ExecutionStopped) as exc: control.check()
        self.assertEqual(exc.exception.code,'timeout')
        control=ExecutionControl(); control.cancel()
        with patch('src.agent.read_response') as model, patch('src.agent.save') as save:
            with self.assertRaises(ExecutionStopped): agent.run('简单问题',execution_control=control)
        model.assert_not_called()
        self.assertEqual(save.call_args.kwargs['stop_reason'],'cancelled')

    def test_cancel_after_model_stops_following_tool(self):
        control=ExecutionControl()
        def response(*args,**kwargs):
            control.cancel()
            return {'content':None,'tool_calls':[{'id':'x','function':{'name':'calc','arguments':'{"expression":"1+1"}'}}]}
        with patch('src.agent.read_response',side_effect=response), patch('src.agent.run_tool_details') as tool, patch('src.agent.save'):
            with self.assertRaises(ExecutionStopped): agent.run('计算',execution_control=control)
        tool.assert_not_called()

    def test_disconnect_cancels_chat_and_releases_lock(self):
        finished=threading.Event()
        def fake_run(question, *, execution_control, **kwargs):
            try:
                while not finished.wait(.01): execution_control.check()
                execution_control.check()
            finally:
                finished.set()
        class Request:
            async def is_disconnected(self): return False
        async def exercise():
            sessions['disconnect-test']=[]
            with patch.object(stream,'PROJECT',self.root), patch.object(stream,'run',side_effect=fake_run):
                response=await server.chat(Request(),server.ChatRequest(session_id='disconnect-test',question='测试'))
                first=await response.body_iterator.__anext__()
                self.assertIn('"type": "user"',first)
                await response.body_iterator.aclose()
                self.assertTrue(await asyncio.to_thread(finished.wait,2))
                self.assertTrue(await asyncio.to_thread(self.wait_for_lock))
            sessions.pop('disconnect-test',None)
        asyncio.run(exercise())

    def test_ticket_disconnect_does_not_cancel_background_execution(self):
        entered, release, finished=threading.Event(),threading.Event(),threading.Event()
        def fake_runner(ticket_id, *, on_event, execution_control, **kwargs):
            on_event({'type':'question_start','question':'测试'})
            entered.set(); release.wait(3)
            execution_control.check()
            finished.set()
            return {'status':'completed'}
        class Request:
            async def is_disconnected(self): return False
        async def exercise():
            with patch.object(super_api.orchestrator,'run_approved',side_effect=fake_runner):
                response=await super_api.run_ticket(Request(),'id',super_api.RunRequest())
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                first=await response.body_iterator.__anext__()
                self.assertIn('question_start',first)
                await response.body_iterator.aclose()
                release.set()
                self.assertTrue(await asyncio.to_thread(finished.wait,2))
                self.assertTrue(await asyncio.to_thread(self.wait_for_lock))
        asyncio.run(exercise())

    def wait_for_lock(self):
        if busy.acquire(timeout=2):
            busy.release(); return True
        return False

    def test_concurrency_is_rejected_then_lock_released(self):
        entered, release=threading.Event(),threading.Event()
        def fake_run(question, **kwargs):
            entered.set(); release.wait(3); return '答案'
        with patch.object(stream,'PROJECT',self.root), patch.object(stream,'run',side_effect=fake_run):
            with TestClient(server.app) as client, ThreadPoolExecutor(max_workers=2) as pool:
                session=client.post('/api/session').json()['session_id']
                body={'session_id':session,'question':'测试'}
                future=pool.submit(client.post,'/chat',json=body)
                self.assertTrue(entered.wait(2))
                for _ in range(9): self.assertEqual(client.post('/chat',json=body).status_code,409)
                release.set()
                self.assertEqual(future.result(timeout=4).status_code,200)
                self.assertTrue(self.wait_for_lock())

    def test_ticket_deadline_preserves_completed_question(self):
        db=self.root/'ticket.db'
        ticket,_=tickets.create_ticket(Mandate('timeout-test','cli','local','explicit','listed','v1'),['一','二'],db)
        clock=[0.0]; control=ExecutionControl(1,clock=lambda:clock[0]); calls=[]
        def agent_stub(question, **kwargs): calls.append(question); return '答案'
        def observer(event):
            if event['type']=='question_done': clock[0]=2
        result=run_ticket(ticket,path=db,agent=agent_stub,on_event=observer,execution_control=control)
        self.assertEqual(result['status'],'failed')
        self.assertEqual([q['status'] for q in result['questions']],['completed','failed'])
        self.assertIn('时间限制',result['questions'][1]['error'])
        self.assertEqual(calls,['一'])
        result=run_ticket(ticket,path=db,agent=agent_stub,retry_failed=True,
                          summarizer=lambda *a,**k:{'answer':'总答','usage':{}})
        self.assertEqual(result['status'],'completed')
        self.assertEqual(calls,['一','二'])


if __name__=='__main__': unittest.main()
