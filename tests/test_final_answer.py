import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.super_agent import tickets
from src.super_agent.domain import Mandate
from src.super_agent.final_answer import synthesize
from src.super_agent.ticket_runner import run_ticket


class FinalAnswerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'tickets.db'
        grant = Mandate('trigger-final', 'cli', 'local', 'explicit', 'listed', 'v1')
        self.id, _ = tickets.create_ticket(grant, ['解释 A', '解释 B'], self.path, original_goal='比较 A 和 B')

    def test_final_uses_goal_questions_evidence_and_stream(self):
        events = []
        source = 'DuReader:' + 'a' * 32
        def agent(question, history, observer, **kwargs):
            observer({'type':'tool', 'name':'search_docs', 'success':True,
                      'result':json.dumps([{'source':source,'text':'资料内容'}]), 'arguments':'{}'})
            return question + '的回答'
        def response(messages, tools, usage, on_delta, **kwargs):
            self.assertIsNone(tools)
            self.assertIn('200 至 350 字', messages[0]['content'])
            self.assertIn('正文用简短的 [1]', messages[0]['content'])
            self.assertIn('每条只写一次完整 DuReader 段落 ID', messages[0]['content'])
            self.assertIn('比较 A 和 B', messages[1]['content'])
            self.assertIn('解释 A的回答', messages[1]['content'])
            self.assertIn(source, messages[1]['content'])
            usage.update(input=20, output=10)
            on_delta('综合 ✅')
            return {'content':'综合 ✅ [' + source + ']'}
        with patch('src.super_agent.final_answer.read_response', side_effect=response):
            result = run_ticket(self.id, path=self.path, agent=agent, on_event=events.append, summarizer=synthesize)
        self.assertEqual(result['status'], 'completed')
        self.assertIn(source, result['final_answer']['answer'])
        self.assertEqual(result['final_answer']['input_tokens'], 20)
        self.assertIn('final_delta', [e['type'] for e in events])

    def test_failed_final_retry_does_not_repeat_questions(self):
        calls = []
        def agent(q, **kwargs):
            calls.append(q)
            return '子回答'
        def fail(*args, **kwargs): raise RuntimeError('模拟汇总失败')
        failed = run_ticket(self.id, path=self.path, agent=agent, summarizer=fail)
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['final_answer']['status'], 'failed')
        final = run_ticket(self.id, path=self.path, retry_failed=True, agent=agent,
                           summarizer=lambda *a, **k:{'answer':'汇总成功','usage':{}})
        self.assertEqual(calls, ['解释 A', '解释 B'])
        self.assertEqual(final['final_answer']['attempt'], 2)
        self.assertEqual(final['status'], 'completed')

    def test_pause_at_boundary_before_summary(self):
        def agent(q, **kwargs):
            if q == '解释 B': tickets.request_pause(self.id, self.path)
            return '子回答'
        paused = run_ticket(self.id, path=self.path, agent=agent)
        self.assertEqual(paused['status'], 'paused')
        self.assertIsNone(paused['final_answer'])
        final = run_ticket(self.id, path=self.path, agent=agent,
                           summarizer=lambda *a, **k:{'answer':'恢复汇总','usage':{}})
        self.assertEqual(final['final_answer']['answer'], '恢复汇总')

    def test_medical_fallback_applies_to_original_goal(self):
        item={'goal':'孕妇用药剂量是多少', 'prior_history':[], 'questions':[], 'evidence':[]}
        with patch('src.super_agent.final_answer.read_response') as model:
            result=synthesize(item)
        model.assert_not_called()
        self.assertIn('医生', result['answer'])


if __name__ == '__main__': unittest.main()
