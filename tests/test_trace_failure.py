import sqlite3
import unittest
from unittest.mock import patch
from src import agent


class TraceFailureTest(unittest.TestCase):
    def test_db_failure_does_not_discard_answer(self):
        events = []
        with patch.object(agent, '_run', return_value='答案'), \
             patch.object(agent, 'save', side_effect=sqlite3.OperationalError('database locked')):
            self.assertEqual(agent.run('q', observer=events.append), '答案')
        self.assertIn('保存失败', events[-1]['content'])

    def test_db_failure_does_not_mask_original_error(self):
        with patch.object(agent, '_run', side_effect=ValueError('原始错误')), \
             patch.object(agent, 'save', side_effect=sqlite3.OperationalError('database locked')):
            with self.assertRaisesRegex(ValueError, '原始错误'):
                agent.run('q')
