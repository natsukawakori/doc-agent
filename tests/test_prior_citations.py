import json
import unittest
from unittest.mock import patch
from src.agent import _run


class PriorCitationTest(unittest.TestCase):
    def test_prior_successful_source_is_valid_but_unknown_id_warns(self):
        valid='a'*32; unknown='b'*32
        prior=[{'name':'search_docs','success':True,'result':json.dumps([{'source':'DuReader:'+valid}])}]
        for answer,should_warn in [('引用 '+valid,False),('引用 '+unknown,True)]:
            events=[]
            state={'calls':[],'answer':None,'tokens':0,'usage_complete':True,'observer':events.append,'prior_evidence':prior}
            with patch('src.agent.read_response',return_value={'role':'assistant','content':answer}):
                self.assertEqual(_run('问题',2,state,[]),answer)
            self.assertEqual(any(e.get('guard')=='citation' for e in events),should_warn)
