import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from src.memory import compress


class MemoryObservationTest(unittest.TestCase):
    def test_records_provider_usage_and_preserves_recent(self):
        history = [{'role': 'user', 'content': '旧信息' * 10}, {'role': 'assistant', 'content': '最近回复'}]
        response = NS(choices=[NS(message=NS(content='摘要'))], usage=NS(prompt_tokens=11, completion_tokens=3))
        events = []
        with patch('src.memory.chat', return_value=response):
            result = compress(history, threshold=1, keep=1, observer=events.append)
        self.assertEqual(result[-1], history[-1])
        self.assertEqual(events[0]['summary_input_tokens'], 11)
        self.assertEqual(events[0]['summary_output_tokens'], 3)
        self.assertLess(events[0]['after_chars'], events[0]['before_chars'])
