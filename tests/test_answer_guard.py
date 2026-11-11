import json
import unittest
from unittest.mock import patch
from src.agent import run, _run
from src.answer_guard import medical_fallback, citation_notice, risk_category, evidence_notice


class AnswerGuardTest(unittest.TestCase):
    def test_medical_fallback_does_not_call_model_or_stream_danger(self):
        chunks, events = [], []
        with patch('src.agent.read_response') as model, patch('src.agent.save') as save:
            answer = run('辅酶 Q10 应该服用多少剂量？', on_delta=chunks.append, observer=events.append)
        model.assert_not_called()
        self.assertEqual(''.join(chunks), answer)
        self.assertIn('未经医学核验', answer)
        self.assertTrue(any(e.get('guard') == 'medical_scope' for e in events))
        self.assertEqual(save.call_args.kwargs['stop_reason'], 'medical_scope')

    def test_risk_rules_are_narrow_and_do_not_claim_coverage(self):
        self.assertIsNotNone(medical_fallback('伤口多久拆线？'))
        self.assertIsNotNone(medical_fallback('这种药一次吃多少？'))
        self.assertIsNotNone(medical_fallback('孕妇缺碘怎么办？'))
        self.assertIsNotNone(medical_fallback('前列腺偏大怎么办？'))
        self.assertIsNotNone(medical_fallback('白醋能去斑吗？'))
        self.assertIsNotNone(medical_fallback('那要吃多少？', [{'role':'user','content':'我在了解辅酶Q10'}]))
        self.assertIsNone(medical_fallback('那要多少？', [{'role':'user','content':'我在比较两种方案'}]))
        self.assertIsNone(medical_fallback('这本书的用量统计是多少？'))
        self.assertIsNone(medical_fallback('游戏药水配方是什么？'))

    def test_topic_and_action_and_multiturn(self):
        for text in ('什么中药可以治疗糖尿病', '孕妇疥疮', '宝宝吃什么长高', '奶粉过稀', '怀孕多吃水果好吗'):
            self.assertEqual(risk_category(text), 'medical_scope', text)
        self.assertEqual(risk_category('柴油车结蜡怎么办'), 'physical_safety_scope')
        self.assertEqual(risk_category('那怎么办', [{'role':'user','content':'孕妇疥疮'}]), 'medical_scope')
        self.assertIsNone(risk_category('给宝宝起个名字'))
        self.assertIsNone(risk_category('孕期摄影怎么构图'))
        self.assertEqual(risk_category('降压药应该吃几片'), 'medical_scope')
        self.assertEqual(risk_category('孕妇血压偏高'), 'medical_scope')
        self.assertEqual(risk_category('小孩眼睛大小不一样'), 'medical_scope')
        self.assertEqual(risk_category('我家宝宝晚上哭闹怎么办'), 'medical_scope')
        self.assertEqual(risk_category('中 药 怎么 治疗 糖尿病'), 'medical_scope')
        self.assertIsNone(risk_category('学生如何激发学习兴趣'))
        self.assertIsNone(risk_category('柴油车模型多少钱'))

    def test_unknown_evidence_does_not_treat_score_as_trust(self):
        data=json.dumps([{'source':'DuReader:'+'a'*32,'text':'资料','rerank_score':0.999}])
        calls=[{'name':'search_docs','success':True,'result':data}]
        self.assertIn('不能证明',evidence_notice(calls))
        self.assertIsNone(evidence_notice([{'name':'search_docs','success':True,'result':'[]'}]))
        self.assertIsNone(evidence_notice([]))

    def test_citation_checks_ids_from_successful_search_only(self):
        valid = 'a'*32
        calls = [{'name':'search_docs','success':True,'result':json.dumps([{'source':'DuReader:'+valid,'text':'证据'}])}]
        self.assertIsNone(citation_notice('根据资料 [DuReader:'+valid+']', calls))
        self.assertIn('未在本轮', citation_notice('根据资料 [DuReader:'+'b'*32+']', calls))
        self.assertIn('未包含', citation_notice('没有来源', calls))
        self.assertIn('未返回', citation_notice('没有来源', [{'name':'search_docs','success':True,'result':'[]'}]))
        self.assertIsNone(citation_notice('答案', []))

    def test_notice_reaches_observer_and_answer(self):
        source = 'a'*32
        result = json.dumps([{'source':'DuReader:'+source,'text':'证据'}])
        call = {'id':'c','type':'function','function':{'name':'search_docs','arguments':'{"query":"q"}'}}
        messages = [{'role':'assistant','content':None,'tool_calls':[call]},
                    {'role':'assistant','content':'错误引用 '+ 'b'*32}]
        events=[]
        state={'calls':[],'answer':None,'tokens':0,'usage_complete':True,'observer':events.append}
        with patch('src.agent.read_response',side_effect=messages), patch('src.agent.run_tool_details',return_value=(result,True)):
            answer = _run('问题',2,state,[])
        self.assertEqual(answer, '错误引用 '+ 'b'*32)
        self.assertTrue(any(e.get('guard')=='citation' for e in events))


if __name__ == '__main__':
    unittest.main()
