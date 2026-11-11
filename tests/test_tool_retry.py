import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from src.agent import run_tool_details
from src.tools.registry import limits
from src.agent import tool_error_message


def result(data):
    return SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr='')


class RetryTest(unittest.TestCase):
    def test_per_tool_limits_and_network_classification(self):
        self.assertEqual(limits('search_docs'), (300, 1))
        self.assertEqual(limits('calc'), (30, 1))
        self.assertEqual(json.loads(tool_error_message('web_fetch', 'URLError: offline'))['error_type'], 'network_error')
    def test_timeout_retries_once(self):
        with patch('src.tool_dispatch.run_worker', side_effect=[subprocess.TimeoutExpired('x', 1), result({'result':'ok'})]) as call:
            response, success = run_tool_details('calc', {'expression':'1'})
            self.assertEqual((response, success), ('ok', True))
            self.assertEqual(response.attempts, 2)
            self.assertEqual(call.call_count, 2)

    def test_invalid_arguments_are_not_retried(self):
        with patch('src.tool_dispatch.run_worker', return_value=result({'error':'ValueError: bad arguments'})) as call:
            self.assertFalse(run_tool_details('calc', {})[1])
            self.assertEqual(call.call_count, 1)

    def test_network_error_retries(self):
        with patch('src.tool_dispatch.run_worker', side_effect=[result({'error':'URLError: unavailable'}), result({'result':'ok'})]) as call:
            self.assertEqual(run_tool_details('web_fetch', {'url':'https://example.com'}), ('ok', True))
            self.assertEqual(call.call_count, 2)
