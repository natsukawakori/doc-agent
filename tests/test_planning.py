import json
import tempfile
import unittest
from unittest.mock import patch as mock_patch
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from src.super_agent import simulation, orchestrator, tickets
from src.super_agent.ticket_runner import run_ticket


class PlanningTest(unittest.TestCase):
    def setUp(self):
        patcher = mock_patch('src.super_agent.ticket_runner.synthesize', return_value={'answer':'综合答案','usage':{}})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.sim=Path(self.tmp.name)/'sim.db'; self.db=Path(self.tmp.name)/'tickets.db'
        self.trigger=simulation.emit('owner','submit','比较 A 和 B 并给出处',['比较 A 和 B 并给出处'],self.sim)

    def test_planning_persists_and_goal_reaches_all_questions(self):
        calls=[]
        def plan(trigger):
            calls.append(trigger.id)
            return {'questions':['解释 A','解释 B','比较前两者'], 'reason':'先分解再比较'}
        result=orchestrator.process(self.trigger.id,'auto',sim_db=self.sim,ticket_db=self.db,plan=True,planner=plan)
        duplicate=orchestrator.process(self.trigger.id,'auto',sim_db=self.sim,ticket_db=self.db,plan=True,planner=plan)
        self.assertEqual(result['ticket_id'],duplicate['ticket_id']); self.assertEqual(len(calls),1)
        self.assertEqual(json.loads(result['plan_json'])['reason'],'先分解再比较')
        record=tickets.get_ticket(result['ticket_id'],self.db)
        self.assertEqual(record['original_goal'],'比较 A 和 B 并给出处')
        self.assertEqual([q['question'] for q in record['questions']],['解释 A','解释 B','比较前两者'])
        seen=[]
        def agent(question,history,observer,retrieval_level):
            seen.append((question,history)); return '答案'
        result=run_ticket(record['id'],path=self.db,agent=agent)
        self.assertEqual(result['status'],'completed')
        self.assertTrue(all('比较 A 和 B 并给出处' in str(history) for _,history in seen))

    def test_requeue_when_only_final_summary_remains(self):
        event=simulation.emit('owner','inferred','比较 A 和 B',['解释 A','解释 B'],self.sim)
        check=lambda *a:{'matches':['doc_question'],'reason':'匹配'}
        orchestrator.configure('auto',sim_db=self.sim,ticket_db=self.db)
        accepted=orchestrator.process(event.id,'auto',sim_db=self.sim,ticket_db=self.db,assessor=check)
        ticket_id=accepted['ticket_id']; called=[]
        def agent(q, **kwargs):
            called.append(q)
            if q=='解释 B': tickets.request_pause(ticket_id,self.db)
            return '回答 '+q
        first=orchestrator.run_approved(ticket_id,sim_db=self.sim,ticket_db=self.db,agent=agent)
        self.assertEqual(first['status'],'paused')
        orchestrator.configure('observe',sim_db=self.sim,ticket_db=self.db)
        denied=orchestrator.run_approved(ticket_id,sim_db=self.sim,ticket_db=self.db,agent=agent)
        self.assertEqual(denied['status'],'resume_denied')
        orchestrator.configure('auto',sim_db=self.sim,ticket_db=self.db)
        resumed=orchestrator.process(denied['requeued_trigger_id'],'auto',sim_db=self.sim,ticket_db=self.db,assessor=check)
        new_id=resumed['ticket_id']
        def summarize(item, **kwargs):
            self.assertEqual(item['goal'],'比较 A 和 B')
            self.assertEqual(len(item['prior_history']),4)
            return {'answer':'汇总结果','usage':{}}
        final=orchestrator.run_approved(new_id,sim_db=self.sim,ticket_db=self.db,agent=agent,summarizer=summarize)
        self.assertEqual(final['status'],'completed')
        self.assertEqual(final['questions'],[])
        self.assertEqual(called,['解释 A','解释 B'])

    def test_no_planning_before_accept_and_bad_plan_can_retry(self):
        visitor=simulation.emit('visitor','submit','目标',['目标'],self.sim)
        def forbidden(t): raise AssertionError('没有授权时不得规划')
        self.assertEqual(orchestrator.process(visitor.id,'auto',sim_db=self.sim,ticket_db=self.db,plan=True,planner=forbidden)['verdict'],'IGNORE')
        infer=simulation.emit('owner','inferred','目标',['目标'],self.sim)
        observed=orchestrator.process(infer.id,'observe',sim_db=self.sim,ticket_db=self.db,plan=True,planner=forbidden,
                                     assessor=lambda *a:{'matches':['doc_question'],'reason':'匹配'})
        self.assertEqual(observed['verdict'],'WOULD_ACCEPT'); self.assertFalse(self.db.exists())
        result=orchestrator.process(self.trigger.id,'auto',sim_db=self.sim,ticket_db=self.db,plan=True,planner=lambda t:{'questions':[]})
        self.assertEqual(result['verdict'],'UNAVAILABLE'); self.assertIn('规划失败',result['reason'])
        self.assertEqual(simulation.get_event(self.trigger.id,self.sim)['status'],'pending')
        result=orchestrator.process(self.trigger.id,'auto',sim_db=self.sim,ticket_db=self.db,planner=lambda t:{'questions':['问题'],'reason':'单题'})
        self.assertEqual(result['verdict'],'ACCEPT')
        self.assertEqual(json.loads(result['plan_json'])['questions'],['问题'])

    def test_observed_event_can_be_reassessed_after_policy_change(self):
        event=simulation.emit('owner','inferred','比较 A 和 B',['比较 A 和 B'],self.sim,plan_requested=True)
        orchestrator.configure('observe',sim_db=self.sim,ticket_db=self.db)
        check=lambda *a:{'matches':['doc_question'],'reason':'匹配'}
        observed=orchestrator.process(event.id,'observe',sim_db=self.sim,ticket_db=self.db,assessor=check)
        self.assertEqual(observed['verdict'],'WOULD_ACCEPT')
        orchestrator.configure('auto',sim_db=self.sim,ticket_db=self.db)
        accepted=orchestrator.process(event.id,'auto',sim_db=self.sim,ticket_db=self.db,assessor=check,
                                      planner=lambda t:{'questions':['比较 A 和 B'],'reason':'单题'})
        self.assertEqual(accepted['verdict'],'ACCEPT')
        self.assertIsNotNone(accepted['plan_json'])
        with simulation.database(self.sim) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sim_decision_history WHERE trigger_id=?',(event.id,)).fetchone()[0],1)

    def test_real_response_parser_rejects_invalid_structure(self):
        response=NS(choices=[NS(message=NS(content='```json\n{"questions":["问题"],"reason":"单题"}\n```'))],usage=NS(prompt_tokens=10,completion_tokens=5))
        with patch('src.super_agent.orchestrator.chat',return_value=response):
            self.assertEqual(orchestrator.model_plan(self.trigger)['questions'],['问题'])
            response.choices[0].message.content='{"questions":[],"reason":"错误"}'
            with self.assertRaises(ValueError): orchestrator.model_plan(self.trigger)

    def test_stale_assessor_cannot_commit_after_recovery(self):
        event=simulation.emit('owner','inferred','任务',['任务'],self.sim)
        started,release=threading.Event(),threading.Event()
        def slow(*a):
            started.set(); release.wait(5)
            return {'matches':['doc_question'],'reason':'旧研判'}
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(orchestrator.process,event.id,'auto',sim_db=self.sim,ticket_db=self.db,assessor=slow)
            self.assertTrue(started.wait(5))
            orchestrator.recover_assessment(event.id,sim_db=self.sim)
            newer=orchestrator.process(event.id,'auto',sim_db=self.sim,ticket_db=self.db,
                                      assessor=lambda *a:{'matches':['doc_question'],'reason':'新研判'})
            release.set(); older=future.result(timeout=5)
        self.assertEqual(newer['verdict'],'ACCEPT')
        self.assertEqual(older['verdict'],'UNAVAILABLE')
        self.assertIn('失效',older['reason'])
