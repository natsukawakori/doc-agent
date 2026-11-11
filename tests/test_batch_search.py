import json
import unittest
from unittest.mock import patch
from src.agent import _run
from src.batch_dispatch import run_batch


def call(identifier, query):
    return {"id": identifier, "type": "function", "function": {
        "name": "search_docs", "arguments": json.dumps({"query": query})}}


class BatchTest(unittest.TestCase):
    def test_invalid_duplicate_mixed_and_budget_do_not_batch(self):
        a, b = call("a", "甲"), call("b", "乙")
        self.assertIsNone(run_batch([a, call("b", "甲")], 8, {}))
        self.assertIsNone(run_batch([a, b], 1, {}))
        self.assertIsNone(run_batch([a, {"function": {"name": "calc", "arguments": "{}"}}], 8, {}))

    def test_agent_keeps_separate_results_and_tool_call_ids(self):
        calls = [call("one", "甲"), call("two", "乙")]
        messages = [{"role": "assistant", "content": None, "tool_calls": calls},
                    {"role": "assistant", "content": "完成"}]
        state = {"calls": [], "answer": None, "tokens": 0, "usage_complete": True}
        observed = []
        state["observer"] = observed.append
        with patch("src.agent.read_response", side_effect=messages), \
             patch("src.agent.run_batch", return_value=(["结果甲", "结果乙"], 12.5)), \
             patch("src.agent.run_tool_details") as single:
            self.assertEqual(_run("问题", 8, state, []), "完成")
        single.assert_not_called()
        self.assertEqual([x["result"] for x in state["calls"]], ["结果甲", "结果乙"])
        self.assertTrue(all(x["shared_batch"] for x in state["calls"]))
        self.assertEqual([x["result"] for x in observed if x["type"] == "tool"], ["结果甲", "结果乙"])


if __name__ == "__main__":
    unittest.main()
