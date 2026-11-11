import json
import unittest
from unittest.mock import patch

from src.tools import registry, web_search
from src.agent import _run
from src.answer_guard import citation_notice


class WebSearchTest(unittest.TestCase):
    def test_citing_actual_web_source_does_not_require_unrelated_local_id(self):
        calls = [
            {"name": "search_docs", "success": True, "result": json.dumps([{"source": "DuReader:" + "a" * 32}])},
            {"name": "web_search", "success": True, "result": json.dumps({"results": [{"url": "https://example.org/doc"}]})},
        ]
        self.assertIsNone(citation_notice("资料 https://example.org/doc", calls))
        self.assertIsNotNone(citation_notice("资料 https://other.example/doc", calls))
        self.assertIsNotNone(citation_notice("资料 https://example.org/doc [DuReader:" + "b" * 32 + "]", calls))

    def test_registered_schema_and_result(self):
        self.assertIn("web_search", [item["function"]["name"] for item in registry.schemas()])
        with patch("ddgs.DDGS") as client:
            client.return_value.text.return_value = [
                {"title": "文档", "href": "https://example.org/doc", "body": "摘要"},
                {"title": "无效", "href": "file:///tmp/a", "body": ""},
            ]
            result = json.loads(registry.execute("web_search", {"query": "示例"}))
        self.assertEqual(result["results"], [{"title": "文档", "url": "https://example.org/doc", "snippet": "摘要"}])
        client.return_value.text.assert_called_once_with("示例", max_results=5)

    def test_empty_query_and_provider_failure(self):
        with self.assertRaises(ValueError):
            web_search.run("   ")
        with patch("ddgs.DDGS") as client:
            client.return_value.text.side_effect = RuntimeError("搜索不可用")
            with self.assertRaisesRegex(RuntimeError, "搜索不可用"):
                web_search.run("示例")

    def test_agent_reports_local_and_web_actions_in_order(self):
        def call(name, query, call_id):
            return {"id": call_id, "type": "function", "function": {
                "name": name, "arguments": json.dumps({"query": query})}}
        replies = [
            {"role": "assistant", "content": None, "tool_calls": [call("search_docs", "q", "1")]},
            {"role": "assistant", "content": None, "tool_calls": [call("web_search", "q", "2")]},
            {"role": "assistant", "content": "网页资料：https://example.org"},
        ]
        events = []
        state = {"calls": [], "answer": None, "tokens": 0, "usage_complete": True, "observer": events.append}
        with patch("src.agent.read_response", side_effect=replies), patch(
            "src.agent.run_tool_details", side_effect=[("本地没有足够信息", True), ("网页摘要", True)]
        ):
            self.assertIn("https://example.org", _run("问题", 8, state, []))
        self.assertEqual([event["name"] for event in events if event["type"] == "tool"],
                         ["search_docs", "web_search"])


if __name__ == "__main__":
    unittest.main()
