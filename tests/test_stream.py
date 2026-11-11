"""流式文字和工具参数分片的拼接测试。"""
import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace as NS
from unittest.mock import patch
from src.agent import read_response


def chunk(content=None, parts=None, reasoning=None):
    delta = NS(content=content, tool_calls=parts, reasoning_content=reasoning)
    return NS(choices=[NS(delta=delta)])


def part(index, call_id, name, arguments):
    return NS(index=index, id=call_id, function=NS(name=name, arguments=arguments))


class StreamTest(unittest.TestCase):
    def test_text_and_fragmented_tool_call(self):
        stream = [chunk("先", reasoning="思"), chunk("读取", reasoning="考"),
                  chunk(parts=[part(0, "call_1", "read_", '{"pa')]),
                  chunk(parts=[part(0, None, "file", 'th":"x"}')])]
        output = io.StringIO()
        with patch("src.agent.chat", return_value=iter(stream)), redirect_stdout(output):
            message = read_response([], [])
        self.assertEqual(output.getvalue(), "[助手] 先读取\n")
        self.assertEqual(message["reasoning_content"], "思考")
        self.assertEqual(message["tool_calls"][0]["function"],
                         {"name": "read_file", "arguments": '{"path":"x"}'})
        self.assertEqual(message["tool_calls"][0]["id"], "call_1")

    def test_gbk_console_does_not_break_emoji_or_tex_stream(self):
        raw = io.BytesIO()
        output = io.TextIOWrapper(raw, encoding="gbk", errors="strict", write_through=True)
        parts = []
        with patch("src.agent.chat", return_value=iter([chunk("✅ "), chunk(r"$x_i^2$")])), redirect_stdout(output):
            message = read_response([], [], on_delta=parts.append)
        output.flush()
        self.assertEqual(message["content"], r"✅ $x_i^2$")
        self.assertEqual("".join(parts), r"✅ $x_i^2$")
        self.assertIn(r"\u2705", raw.getvalue().decode("gbk"))
        output.detach()


if __name__ == "__main__":
    unittest.main()
