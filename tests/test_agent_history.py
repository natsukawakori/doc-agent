import unittest
from unittest.mock import patch
from src.agent import _run


class AgentHistoryTest(unittest.TestCase):
    def test_history_is_sent_before_current_question(self):
        history = [{'role': 'user', 'content': '暗号是蓝色'}, {'role': 'assistant', 'content': '收到'}]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        observed = []
        def response(messages, tools, usage):
            observed.extend(messages)
            return {'role': 'assistant', 'content': '蓝色'}
        with patch('src.agent.read_response', side_effect=response):
            result = _run('暗号是什么？', 8, state, history)
        self.assertEqual(result, '蓝色')
        self.assertEqual(observed[1:3], history)
        self.assertEqual(observed[-1]['content'], '暗号是什么？')
        self.assertEqual(state['answer'], '蓝色')


if __name__ == '__main__':
    unittest.main()
