import unittest
from unittest.mock import patch
from src import agent


class IdleGuardTest(unittest.TestCase):
    def test_repeat_result_stops_and_disables_tools(self):
        call = {'id': '1', 'type': 'function', 'function': {'name': 'calc', 'arguments': '{"expression":"1+1"}'}}
        replies = [{'content': None, 'tool_calls': [call]}, {'content': None, 'tool_calls': [call]}, {'content': '停止'}]
        observed = []
        def respond(messages, tools, *args):
            observed.append(tools)
            return replies.pop(0)
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.object(agent, 'read_response', side_effect=respond), patch.object(agent, 'run_tool_details', return_value=('2', True)):
            self.assertEqual(agent._run('test', 8, state, []), '停止')
        self.assertEqual(len(state['calls']), 2)
        self.assertIsNone(observed[-1])
