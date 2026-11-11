import json
import unittest
from unittest.mock import patch
import src.agent as agent


class ToolFeedbackTest(unittest.TestCase):
    def test_failure_is_structured_and_followup_can_change_strategy(self):
        call = {'id': 'x', 'type': 'function', 'function': {'name': 'calc', 'arguments': '{bad'}}
        replies = [{'content': None, 'tool_calls': [call]}, {'content': '参数不正确'}]
        seen = []
        def respond(messages, *args):
            seen.append(list(messages))
            return replies.pop(0)
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.object(agent, 'read_response', side_effect=respond):
            self.assertEqual(agent._run('测试', 2, state, []), '参数不正确')
        feedback = json.loads(seen[1][-1]['content'])
        self.assertEqual(feedback['tool'], 'calc')
        self.assertEqual(feedback['error_type'], 'invalid_arguments')
        self.assertEqual(len(state['calls']), 1)
