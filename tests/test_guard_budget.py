import unittest
from unittest.mock import patch
from src.guard import budget_status
from src.agent import _run


class BudgetTest(unittest.TestCase):
    def test_budget_and_missing_usage(self):
        self.assertIsNone(budget_status(5, True, 10))
        self.assertEqual(budget_status(10, True, 10), 'token_budget')
        self.assertEqual(budget_status(5, False, 10), 'usage_unavailable')
        self.assertIsNone(budget_status(0, False, None))
        with self.assertRaises(ValueError):
            budget_status(0, True, 0)

    def test_missing_usage_prevents_tool_execution(self):
        call = {'id': '1', 'type': 'function', 'function': {'name': 'calc', 'arguments': '{"expression":"1+1"}'}}
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True, 'token_budget': 10}
        with patch('src.agent.read_response', return_value={'content': None, 'tool_calls': [call]}), \
             patch('src.agent.run_tool_details') as tool:
            self.assertIn('用量不可用', _run('test', 8, state, []))
        tool.assert_not_called()
