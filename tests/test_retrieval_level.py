import json
import unittest
from unittest.mock import patch
from src.agent import _run, run


def state(level, events):
    return {'calls':[],'answer':None,'tokens':0,'usage_complete':True,'observer':events.append,'retrieval_level':level}


class RetrievalLevelTest(unittest.TestCase):
    def test_level_zero_filters_and_blocks_forged_tool_call(self):
        call={'id':'x','type':'function','function':{'name':'web_search','arguments':'{"query":"q"}'}}
        replies=[{'role':'assistant','content':None,'tool_calls':[call]}, {'role':'assistant','content':'未联网'}]
        events=[]
        with patch('src.agent.read_response',side_effect=replies) as model, patch('src.agent.run_tool_details') as execute:
            self.assertEqual(_run('q',2,state(0,events),[]),'未联网')
        execute.assert_not_called()
        names=[x['function']['name'] for x in model.call_args_list[0].args[1]]
        self.assertNotIn('web_search',names); self.assertNotIn('web_fetch',names)
        self.assertFalse(next(e for e in events if e['type']=='tool')['success'])

    def test_level_three_forces_search_before_model_and_exposes_failure(self):
        events=[]; captured=[]
        def model(messages, tools, usage):
            captured.extend(messages)
            return {'role':'assistant','content':'搜索不可用'}
        with patch('src.agent.read_response',side_effect=model), patch('src.agent.run_tool_details',return_value=('网络故障',False)) as tool:
            self.assertEqual(_run('q',2,state(3,events),[]),'搜索不可用')
        tool.assert_called_once_with('web_search',{'query':'q'})
        self.assertEqual(next(e for e in events if e['type']=='tool')['name'],'web_search')
        self.assertFalse(next(e for e in events if e['type']=='tool')['success'])
        self.assertTrue(any('宿主预先执行网页搜索' in m.get('content','') and 'web_search' in m.get('content','') for m in captured if m['role']=='user'))

    def test_invalid_level_and_budget(self):
        with self.assertRaises(ValueError): run('q',retrieval_level=9)
        with self.assertRaises(ValueError): run('q',max_steps=0,retrieval_level=3)
