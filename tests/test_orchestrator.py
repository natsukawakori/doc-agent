import tempfile
import unittest
from unittest.mock import patch as mock_patch
from pathlib import Path
from src.super_agent import orchestrator, simulation, tickets


class OrchestratorTest(unittest.TestCase):
    def setUp(self):
        patcher = mock_patch('src.super_agent.ticket_runner.synthesize', return_value={'answer':'综合答案','usage':{}})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.sim=Path(self.tmp.name)/'sim.sqlite3'; self.tickets=Path(self.tmp.name)/'tickets.sqlite3'

    def emit(self,role,kind):
        return simulation.emit(role,kind,'处理清单',['解释 A','解释 B'],self.sim)

    def process(self,t,mode,assessor):
        return orchestrator.process(t.id,mode,sim_db=self.sim,ticket_db=self.tickets,assessor=assessor)

    def test_modes_observe_evaluates_without_ticket_auto_creates_idempotently(self):
        calls=[]
        def assess(t,questions):
            calls.append(t.id); return {'matches':['doc_question'],'reason':'匹配'}
        off=self.emit('owner','inferred')
        self.assertEqual(self.process(off,'off',assess)['verdict'],'IGNORE')
        self.assertFalse(calls)
        for _ in range(5):
            event=self.emit('owner','inferred')
            result=self.process(event,'observe',assess)
            self.assertEqual(result['verdict'],'WOULD_ACCEPT')
            self.assertIsNone(result['ticket_id'])
        self.assertEqual(len(calls),5)
        self.assertFalse(self.tickets.exists())
        event=self.emit('owner','inferred')
        first=self.process(event,'auto',assess)
        second=self.process(event,'auto',assess)
        self.assertEqual(first['verdict'],'ACCEPT')
        self.assertEqual(first['ticket_id'],second['ticket_id'])
        self.assertEqual(tickets.get_ticket(first['ticket_id'],self.tickets)['status'],'pending')
        self.assertEqual(calls.count(event.id),1)

    def test_explicit_and_visitor_gate_do_not_use_model(self):
        def forbidden(*args): raise AssertionError('不应调用外层模型')
        for mode in ('off','observe','auto'):
            self.assertEqual(self.process(self.emit('owner','submit'),mode,forbidden)['verdict'],'ACCEPT')
            denied=self.process(self.emit('visitor','submit'),mode,forbidden)
            self.assertEqual(denied['verdict'],'IGNORE')
            self.assertIsNone(denied['ticket_id'])

    def test_outer_failure_returns_pending_and_retry_succeeds(self):
        event=self.emit('owner','inferred')
        def fail(*a): raise ValueError('研判不可用')
        self.assertEqual(self.process(event,'auto',fail)['verdict'],'UNAVAILABLE')
        self.assertEqual(simulation.get_event(event.id,self.sim)['status'],'pending')
        result=self.process(event,'auto',lambda *a:{'matches':['doc_question'],'reason':'匹配'})
        self.assertEqual(result['verdict'],'ACCEPT')

    def test_accept_can_finish_ticket_creation_after_interruption(self):
        from unittest.mock import patch
        event=self.emit('owner','submit')
        with patch('src.super_agent.orchestrator.tickets.create_ticket',side_effect=OSError('写入失败')):
            with self.assertRaises(OSError): self.process(event,'auto',lambda *a:None)
        result=self.process(event,'auto',lambda *a:None)
        self.assertEqual(result['verdict'],'ACCEPT')
        self.assertIsNotNone(result['ticket_id'])

    def test_policy_change_during_assessment_requeues_without_ticket(self):
        event=self.emit('owner','inferred')
        orchestrator.configure('auto',sim_db=self.sim,ticket_db=self.tickets)
        def change(*args):
            orchestrator.configure('observe',sim_db=self.sim,ticket_db=self.tickets)
            return {'matches':['doc_question'],'reason':'匹配'}
        result=self.process(event,'auto',change)
        self.assertEqual(result['verdict'],'UNAVAILABLE')
        self.assertEqual(simulation.get_event(event.id,self.sim)['status'],'pending')
        self.assertFalse(self.tickets.exists())
        result=self.process(event,'auto',lambda *a:{'matches':['doc_question'],'reason':'匹配'})
        self.assertEqual(result['verdict'],'WOULD_ACCEPT')

    def test_policy_change_denies_resume_and_requeues_remaining_questions(self):
        orchestrator.configure('auto',sim_db=self.sim,ticket_db=self.tickets)
        event=self.emit('owner','inferred')
        accepted=self.process(event,'auto',lambda *a:{'matches':['doc_question'],'reason':'匹配'})
        ticket=accepted['ticket_id']
        def first_agent(q,history,observer,retrieval_level):
            observer({'type':'tool','name':'search_docs','success':True,'result':'[{"source":"DuReader:'+ 'a'*32 +'"}]','arguments':'{}'})
            return '答案'
        first=orchestrator.run_approved(ticket,sim_db=self.sim,ticket_db=self.tickets,max_questions=1,agent=first_agent)
        self.assertEqual(first['status'],'paused')
        orchestrator.configure('observe',sim_db=self.sim,ticket_db=self.tickets)
        result=orchestrator.run_approved(ticket,sim_db=self.sim,ticket_db=self.tickets,agent=lambda *a,**kw:'不应执行')
        self.assertEqual(result['status'],'resume_denied')
        self.assertEqual(simulation.get_event(result['requeued_trigger_id'],self.sim)['questions'],['解释 B'])
        self.assertEqual(tickets.get_ticket(ticket,self.tickets)['status'],'paused')
        again=orchestrator.run_approved(ticket,sim_db=self.sim,ticket_db=self.tickets)
        self.assertEqual(result,again)
        orchestrator.configure('auto',sim_db=self.sim,ticket_db=self.tickets)
        self.assertEqual(orchestrator.run_approved(ticket,sim_db=self.sim,ticket_db=self.tickets),result)
        replacement=self.process(simulation.to_trigger(simulation.get_event(result['requeued_trigger_id'],self.sim)),
                                 'auto',lambda *a:{'matches':['doc_question'],'reason':'匹配'})
        seen=[]
        def runner(question,history,observer,retrieval_level,prior_evidence=None):
            seen.append((question,history,prior_evidence)); return '后续答案'
        finished=orchestrator.run_approved(replacement['ticket_id'],sim_db=self.sim,ticket_db=self.tickets,agent=runner)
        self.assertEqual(finished['status'],'completed')
        self.assertEqual(seen[0][0],'解释 B')
        self.assertIn('解释 A',str(seen[0][1]))
        self.assertIn('答案',str(seen[0][1]))
        self.assertIn('a'*32,str(seen[0][2]))

    def test_explicit_ticket_resumes_after_mode_change_but_not_identity_removal(self):
        orchestrator.configure('auto',sim_db=self.sim,ticket_db=self.tickets)
        accepted=self.process(self.emit('owner','submit'),'auto',lambda *a:None)
        ticket=accepted['ticket_id']
        orchestrator.run_approved(ticket,sim_db=self.sim,ticket_db=self.tickets,max_questions=1,
                                  agent=lambda q,history,observer,retrieval_level:'答案')
        orchestrator.configure('observe',sim_db=self.sim,ticket_db=self.tickets)
        done=orchestrator.run_approved(ticket,sim_db=self.sim,ticket_db=self.tickets,
                                       agent=lambda q,history,observer,retrieval_level:'答案')
        self.assertEqual(done['status'],'completed')
        other=self.process(self.emit('owner','submit'),'observe',lambda *a:None)['ticket_id']
        orchestrator.configure('observe',owner_allowed=False,sim_db=self.sim,ticket_db=self.tickets)
        self.assertEqual(orchestrator.run_approved(other,sim_db=self.sim,ticket_db=self.tickets)['status'],'resume_denied')

    def test_visitor_explicit_respects_simulated_policy(self):
        orchestrator.configure('off',visitor_allowed=True,sim_db=self.sim,ticket_db=self.tickets)
        event=self.emit('visitor','submit')
        result=self.process(event,'observe',lambda *a: (_ for _ in ()).throw(AssertionError()))
        self.assertEqual(result['verdict'],'ACCEPT')
        self.assertEqual(result['mode'],'off')
