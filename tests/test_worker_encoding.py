"""验证 Windows 默认编码下，工具进程也能返回中文。"""
import os
import unittest
from unittest.mock import patch
from src.agent import run_tool


class WorkerEncodingTest(unittest.TestCase):
    def test_chinese_error_without_encoding_override(self):
        with patch.dict(os.environ):
            os.environ.pop("PYTHONIOENCODING", None)
            result = run_tool("不存在的工具", {})
        self.assertIn("未知工具", result)


if __name__ == "__main__":
    unittest.main()
