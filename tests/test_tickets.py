import tempfile
import threading
import unittest
from unittest.mock import patch as mock_patch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from src.super_agent.domain import Mandate
from src.super_agent import tickets
from src.super_agent.ticket_runner import run_ticket


class TicketTest(unittest.TestCase):
    def setUp(self):
        patcher = mock_patch('src.super_agent.ticket_runner.synthesize', return_value={'answer':'综合答案','usage':{}})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'tickets.sqlite3'
        self.grant = Mandate('trigger-1','cli','local','explicit','listed','v1')
        self.questions = ['解释 A', '解释 B', '比较前面两者']
        self.id, created = tickets.create_ticket(self.grant, self.questions, self.path)
        self.assertTrue(created)

    def test_idempotent_trigger_and_different_payload_rejected(self):
        self.assertEqual(tickets.create_ticket(self.grant, self.questions, self.path), (self.id, False))
        with self.assertRaises(ValueError):
            tickets.create_ticket(self.grant, ['不同内容'], self.path)

    def test_pause_resume_preserves_history_and_events(self):
        seen = []
        def agent(question, history, observer, prior_evidence=None):
            seen.append((question, list(history)))
            observer({'type':'tool','name':'search_docs','result':'资料'})
            return '回答：' + question
        first = run_ticket(self.id, path=self.path, max_questions=1, agent=agent)
        self.assertEqual(first['status'], 'paused')
        self.assertEqual([q['status'] for q in first['questions']], ['completed','pending','pending'])
        final = run_ticket(self.id, path=self.path, agent=agent)
        self.assertEqual(final['status'], 'completed')
        self.assertEqual(len(seen), 3)
        self.assertEqual([m['content'] for m in seen[2][1]], ['解释 A','回答：解释 A','解释 B','回答：解释 B'])
        self.assertEqual(len([e for e in final['events'] if e['event']['type'] == 'tool']), 3)
        lifecycle = [e['event']['type'] for e in final['events'] if e['position'] is None]
        self.assertEqual(lifecycle, ['ticket_created','ticket_started','pause_requested','ticket_paused','ticket_resumed','final_started','final_completed','ticket_completed'])
        self.assertEqual([q['attempt'] for q in final['questions']], [1,1,1])

    def test_failure_requires_explicit_retry_and_preserves_attempt_events(self):
        def fail(question, history, observer):
            observer({'type':'notice','content':'失败前事件'})
            if question == '解释 B': raise RuntimeError('模拟失败')
            return '答案'
        failed = run_ticket(self.id, path=self.path, agent=fail)
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual([q['status'] for q in failed['questions']], ['completed','failed','pending'])
        with self.assertRaises(ValueError):
            run_ticket(self.id, path=self.path, agent=fail)
        final = run_ticket(self.id, path=self.path, retry_failed=True, agent=lambda q,history,observer:'恢复答案')
        self.assertEqual(final['status'], 'completed')
        self.assertEqual([q['attempt'] for q in final['questions']], [1,2,1])
        self.assertTrue(any(e['position'] == 2 and e['attempt'] == 1 and e['event'].get('content') == '失败前事件' for e in final['events']))

    def test_interruption_is_not_silently_retried(self):
        owner = tickets.acquire(self.id, path=self.path)
        tickets.next_question(self.id, owner, path=self.path)
        with self.assertRaises(ValueError):
            tickets.acquire(self.id, path=self.path)
        tickets.recover_interrupted(self.id, path=self.path)
        recovered = tickets.get_ticket(self.id, path=self.path)
        self.assertEqual(recovered['status'], 'failed')
        self.assertEqual(recovered['questions'][0]['status'], 'failed')
        self.assertIn('结果不确定', recovered['questions'][0]['error'])
        with self.assertRaises(RuntimeError):
            tickets.finish_question(self.id, owner, {'position':1,'attempt':1}, answer='旧执行器返回', path=self.path)

    def test_only_successful_prior_tool_evidence_is_passed(self):
        received=[]
        def agent(question,history,observer,prior_evidence=None):
            received.append(prior_evidence)
            if question=='解释 A':
                observer({'type':'tool','name':'search_docs','success':True,'result':'[{"source":"DuReader:'+ 'a'*32 +'"}]','arguments':'{}'})
                observer({'type':'tool','name':'search_docs','success':False,'result':'错误','arguments':'{}'})
            return '答案'
        result=run_ticket(self.id,path=self.path,agent=agent)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(received[1]),1)
        self.assertIn('a'*32,received[1][0]['result'])

    def test_simultaneous_workers_only_one_executes(self):
        entered, release = threading.Event(), threading.Event()
        def agent(question, history, observer):
            entered.set()
            release.wait(5)
            return '答案'
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run_ticket, self.id, path=self.path, agent=agent)
            self.assertTrue(entered.wait(5))
            with self.assertRaises(ValueError):
                run_ticket(self.id, path=self.path, agent=agent)
            tickets.request_pause(self.id, path=self.path)
            release.set()
            self.assertEqual(first.result(timeout=10)['status'], 'paused')
        self.assertEqual([q['attempt'] for q in tickets.get_ticket(self.id, self.path)['questions']], [1,0,0])
