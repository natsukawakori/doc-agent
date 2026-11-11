import tempfile
import unittest
from unittest.mock import patch as mock_patch
from pathlib import Path
from src.super_agent import tickets
from src.super_agent.domain import Mandate
from src.super_agent.ticket_runner import run_ticket


class TicketRetrievalTest(unittest.TestCase):
    def setUp(self):
        patcher = mock_patch('src.super_agent.ticket_runner.synthesize', return_value={'answer':'综合答案','usage':{}})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_policy_versions_and_prior_web_evidence_reach_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'t.sqlite3'
            ticket,_=tickets.create_ticket(Mandate('1','cli','me','explicit','listed','v1'),['一','二'],db)
            tickets.set_retrieval_level(ticket,3,db)
            calls=[]
            def agent(question,history,observer,retrieval_level,prior_evidence=None):
                calls.append((question,history,retrieval_level))
                if question=='一':
                    observer({'type':'tool','name':'web_search','success':True,'result':'先前网页证据','arguments':'{}'})
                    observer({'type':'assistant','content':'正文中出现 question_policy 字样'})
                return '采用之前资料；不需补查。'
            self.assertEqual(run_ticket(ticket,path=db,max_questions=1,agent=agent)['status'],'paused')
            self.assertEqual(tickets.set_retrieval_level(ticket,0,db),2)
            final=run_ticket(ticket,path=db,agent=agent)
            self.assertEqual(final['status'],'completed')
            self.assertEqual([x[2] for x in calls],[3,0])
            self.assertIn('先前网页证据',calls[1][1][-1]['content'])
            self.assertTrue(any(e['event']['type']=='policy_choice_reply_excerpt' for e in final['events']))
            self.assertEqual(final['questions'][0]['answer'],'采用之前资料；不需补查。')

    def test_policy_cannot_change_while_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'t.sqlite3'
            ticket,_=tickets.create_ticket(Mandate('2','cli','me','explicit','listed','v1'),['问题'],db)
            tickets.acquire(ticket,path=db)
            with self.assertRaises(ValueError): tickets.set_retrieval_level(ticket,3,db)
