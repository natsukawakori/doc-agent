import json
import unittest
from unittest.mock import patch
from src import agent


class ErrorStreakTest(unittest.TestCase):
    def test_stops_after_three_and_requests_final_answer(self):
        call = lambda i: {'id': str(i), 'type': 'function', 'function': {'name': 'calc', 'arguments': '{bad'}}
        replies = [{'content': None, 'tool_calls': [call(i)]} for i in range(3)] + [{'content': '工具不可用'}]
        requested = []
        def response(messages, tools, *args):
            requested.append(tools)
            return replies.pop(0)
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.object(agent, 'read_response', side_effect=response):
            self.assertEqual(agent._run('测试', 8, state, []), '工具不可用')
        self.assertEqual(len(state['calls']), 3)
        self.assertIsNone(requested[-1])
        self.assertEqual(json.loads(agent.tool_error_message('calc', '参数错误'))['error_type'], 'invalid_arguments')
