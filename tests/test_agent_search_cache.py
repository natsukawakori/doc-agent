import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

import src.agent as agent


def call(i, query):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": str(i), "type": "function",
            "function": {"name": "search_docs", "arguments": '{"query":"' + query + '"}'}}]}


class SearchCacheTest(unittest.TestCase):
    def test_only_successful_identical_search_is_reused_within_one_run(self):
        responses = [call(1, "a"), call(2, "a"), call(3, "a"),
                     {"role": "assistant", "content": "done"}]
        state = {"calls": [], "answer": None, "tokens": 0, "usage_complete": True}
        with patch.object(agent, "read_response", side_effect=responses), \
             patch.object(agent, "run_tool_details", side_effect=[("temporary error", False),
                                                                  ("A", True)]) as run:
            self.assertEqual(agent._run("test", 8, state, []), "done")
        self.assertEqual(run.call_count, 2)
        self.assertEqual([c["reused"] for c in state["calls"]], [False, False, True])
        self.assertEqual([c["result"] for c in state["calls"]], ["temporary error", "A", "A"])


if __name__ == "__main__":
    unittest.main()
