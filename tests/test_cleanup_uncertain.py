import json
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from src import agent, batch_dispatch, tool_dispatch
from src.process_runner import CleanupUncertainError, run_worker


def call(i, name='calc', args=None):
    return {'id': str(i), 'type': 'function', 'function': {'name': name,
            'arguments': json.dumps(args or {'expression':'1+1'})}}


class CleanupUncertainTest(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows taskkill failure test')
    def test_failed_tree_kill_reports_uncertainty(self):
        proc = MagicMock(pid=12345)
        proc.poll.return_value = None
        proc.communicate.side_effect = [subprocess.TimeoutExpired('x', 1), ('', '')]
        with patch('src.process_runner.subprocess.Popen', return_value=proc), \
             patch('src.process_runner.subprocess.run', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(CleanupUncertainError):
                run_worker(['x'], payload='', cwd=None, timeout=1, env={})
        proc.kill.assert_called_once()

    def test_uncertain_cleanup_is_not_retried(self):
        with patch.object(tool_dispatch, 'run_worker', side_effect=CleanupUncertainError('x', 1)) as worker:
            text, ok = tool_dispatch.run_tool_details('search_docs', {'query':'q'})
        self.assertFalse(ok)
        self.assertIn('清理状态不确定', text)
        self.assertEqual(text.attempts, 1)
        worker.assert_called_once()

    def test_agent_stops_remaining_tools(self):
        calls = [call(1), call(2)]
        replies = [{'content': None, 'tool_calls': calls}, {'content': '已停止'}]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.object(agent, 'read_response', side_effect=replies), \
             patch.object(agent, 'run_tool_details', return_value=('进程树清理状态不确定', False)) as worker:
            self.assertEqual(agent._run('q', 8, state, []), '已停止')
        worker.assert_called_once()
        self.assertEqual(state['stop_reason'], 'cleanup_uncertain')

    def test_batch_does_not_fallback_after_uncertain_cleanup(self):
        calls = [call(1, 'search_docs', {'query':'a'}), call(2, 'search_docs', {'query':'b'})]
        with patch.object(batch_dispatch, 'run_worker', side_effect=CleanupUncertainError('x', 1)):
            with self.assertRaises(CleanupUncertainError):
                batch_dispatch.run_batch(calls, 8, {})

    def test_agent_reports_and_records_batch_cleanup_uncertainty(self):
        calls = [call(1, 'search_docs', {'query':'a'}), call(2, 'search_docs', {'query':'b'})]
        state = {'calls': [], 'answer': None, 'tokens': 0, 'usage_complete': True}
        with patch.object(agent, 'read_response', return_value={'content': None, 'tool_calls': calls}), \
             patch.object(agent, 'run_batch', side_effect=CleanupUncertainError('x', 1)), \
             patch.object(agent, 'run_tool_details') as single:
            answer = agent._run('q', 8, state, [])
        self.assertIn('清理状态不确定', answer)
        self.assertEqual(state['stop_reason'], 'cleanup_uncertain')
        single.assert_not_called()
