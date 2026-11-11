import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from src.memory import compress


class MemoryTest(unittest.TestCase):
    def test_summary_and_recent_history(self):
        history = [{"role": "user", "content": "我喜欢蓝色"}, {"role": "assistant", "content": "记住了"},
                   {"role": "user", "content": "问题二"}, {"role": "assistant", "content": "回答二"}]
        response = NS(choices=[NS(message=NS(content="用户喜欢蓝色"))])
        with patch("src.memory.chat", return_value=response):
            result = compress(history, threshold=2, keep=2)
        self.assertIn("用户喜欢蓝色", result[0]["content"])
        self.assertEqual(result[1:], history[-2:])
        self.assertEqual(len(history), 4)

    def test_short_history_is_untouched(self):
        history = [{"role": "user", "content": "你好"}]
        self.assertIs(compress(history), history)


if __name__ == "__main__":
    unittest.main()
