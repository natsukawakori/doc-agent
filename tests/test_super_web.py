import json
import tempfile
import unittest
from unittest.mock import patch as mock_patch
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.server import app
from app import super_api
from src.super_agent import orchestrator


class SuperWebTest(unittest.TestCase):
    def setUp(self):
        patcher = mock_patch('src.super_agent.ticket_runner.synthesize', return_value={'answer':'综合答案','usage':{}})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.sim=patch.object(super_api,'SIM_DB',root/'simulation.sqlite3'); self.sim.start(); self.addCleanup(self.sim.stop)
        self.tickets=patch.object(super_api,'TICKET_DB',root/'tickets.sqlite3'); self.tickets.start(); self.addCleanup(self.tickets.stop)
        self.client=TestClient(app); self.addCleanup(self.client.close)

    def trigger(self,role='owner',kind='submit'):
        return self.client.post('/api/super/triggers',json={'role':role,'kind':kind,'text':'处理清单',
             'questions':['解释 A','比较前文'], 'retrieval_level':0})

    def test_explicit_ticket_stream_pause_and_resume(self):
        self.assertEqual(self.client.get('/super').status_code,200)
        self.assertEqual(len(self.client.get('/api/super/settings').json()['identities']),3)
        self.client.post('/api/super/policy',json={'mode':'auto'})
        decision=self.trigger().json()['decision']
        self.assertEqual(decision['verdict'],'ACCEPT')
        ticket=decision['ticket_id']; seen=[]
        def fake_agent(question, history, observer, retrieval_level, prior_evidence=None, execution_control=None):
            seen.append((question,history,retrieval_level))
            observer({'type':'model_start'})
            observer({'type':'tool','name':'search_docs','success':True,'arguments':'{}','result':'资料','seconds':0.1})
            return '✅ 答案 $x^2$'
        actual=orchestrator.run_approved
        def fake_runner(*args,**kwargs): return actual(*args,**kwargs,agent=fake_agent)
        with patch.object(super_api.orchestrator,'run_approved',side_effect=fake_runner):
            first=self.client.post(f'/api/super/tickets/{ticket}/run',json={'max_questions':1})
            self.assertEqual(first.status_code,200)
            events=[json.loads(line[6:]) for line in first.text.splitlines() if line.startswith('data: ')]
            self.assertEqual(events[-1]['result']['status'],'paused')
            self.assertTrue(any(x['type']=='agent_event' and x['event'].get('name')=='search_docs' for x in events))
            self.assertEqual(self.client.post(f'/api/super/tickets/{ticket}/retrieval',json={'level':2}).status_code,200)
            second=self.client.post(f'/api/super/tickets/{ticket}/run',json={})
        events=[json.loads(line[6:]) for line in second.text.splitlines() if line.startswith('data: ')]
        self.assertEqual(events[-1]['result']['status'],'completed')
        self.assertEqual([x[2] for x in seen],[0,2])
        self.assertIn('解释 A',str(seen[1][1]))
        self.assertIn('✅',events[-1]['result']['questions'][0]['answer'])

    def test_observe_inferred_calls_outer_but_no_ticket(self):
        self.client.post('/api/super/policy',json={'mode':'observe'})
        response=NS(choices=[NS(message=NS(content='{"match":true,"reason":"文档任务"}'))],usage=NS(prompt_tokens=10,completion_tokens=4))
        with patch('src.super_agent.orchestrator.chat',return_value=response) as model:
            result=self.trigger('owner','inferred').json()['decision']
        model.assert_called_once()
        self.assertEqual(result['verdict'],'WOULD_ACCEPT')
        self.assertIsNone(result['ticket_id'])
        self.assertFalse(super_api.TICKET_DB.exists())

    def test_denied_visitor_and_bot_explicit(self):
        self.client.post('/api/super/policy',json={'mode':'off'})
        self.assertEqual(self.trigger('visitor','submit').json()['decision']['verdict'],'IGNORE')
        self.assertEqual(self.trigger('bot','submit').status_code,400)
        self.assertEqual(self.client.post('/api/super/policy',json={'mode':'auto'},headers={'Origin':'https://example.org'}).status_code,403)

    def test_auto_plan_is_saved_and_used_for_ticket(self):
        self.client.post('/api/super/policy',json={'mode':'observe'})
        response=NS(choices=[NS(message=NS(content='{"questions":["解释 A","比较 A 和 B"],"reason":"比较前先解释"}'))],usage=NS(prompt_tokens=11,completion_tokens=6))
        with patch('src.super_agent.orchestrator.chat',return_value=response):
            result=self.client.post('/api/super/triggers',json={'role':'owner','kind':'submit','text':'比较 A 和 B',
                   'questions':['比较 A 和 B'],'retrieval_level':0,'plan':True}).json()['decision']
        self.assertEqual(result['verdict'],'ACCEPT')
        record=self.client.get('/api/super/tickets/'+result['ticket_id']).json()
        self.assertEqual(record['original_goal'],'比较 A 和 B')
        self.assertEqual([q['question'] for q in record['questions']],['解释 A','比较 A 和 B'])

    def test_policy_denial_requeue_and_resume_with_history(self):
        self.client.post('/api/super/policy',json={'mode':'auto'})
        response=NS(choices=[NS(message=NS(content='{"match":true,"reason":"文档任务"}'))],usage=NS(prompt_tokens=10,completion_tokens=4))
        with patch('src.super_agent.orchestrator.chat',return_value=response):
            ticket=self.trigger('owner','inferred').json()['decision']['ticket_id']
            actual=orchestrator.run_approved; histories=[]
            def fake_agent(question,history,observer,retrieval_level,execution_control=None): histories.append(history); return '已有答案'
            def fake_runner(*args,**kwargs): return actual(*args,**kwargs,agent=fake_agent)
            with patch.object(super_api.orchestrator,'run_approved',side_effect=fake_runner):
                self.client.post(f'/api/super/tickets/{ticket}/run',json={'max_questions':1})
                self.client.post('/api/super/policy',json={'mode':'observe'})
                denied=self.client.post(f'/api/super/tickets/{ticket}/run',json={})
                result=[json.loads(x[6:]) for x in denied.text.splitlines() if x.startswith('data: ')][-1]['result']
                self.assertEqual(result['status'],'resume_denied')
                queued=result['requeued_trigger_id']
                observed=self.client.post(f'/api/super/triggers/{queued}/process',json={'level':0}).json()['decision']
                self.assertEqual(observed['verdict'],'WOULD_ACCEPT')
                self.client.post('/api/super/policy',json={'mode':'auto'})
                accepted=self.client.post(f'/api/super/triggers/{queued}/process',json={'level':0}).json()['decision']
                self.assertEqual(accepted['verdict'],'ACCEPT')
                replacement=accepted['ticket_id']
                done=self.client.post(f'/api/super/tickets/{replacement}/run',json={})
            final=[json.loads(x[6:]) for x in done.text.splitlines() if x.startswith('data: ')][-1]['result']
            self.assertEqual(final['status'],'completed')
            self.assertIn('解释 A',str(histories[-1])); self.assertIn('已有答案',str(histories[-1]))
