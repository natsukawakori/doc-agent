import unittest
from unittest.mock import patch
from src.agent import _run


class AgentEventTest(unittest.TestCase):
    def test_pending_tool_event_precedes_execution(self):
        call = {"id": "call-1", "type": "function", "function": {"name": "calc", "arguments": '{"expression":"1+1"}'}}
        replies = [{"role": "assistant", "content": None, "tool_calls": [call]},
                   {"role": "assistant", "content": "2"}]
        events = []
        state = {"calls": [], "answer": None, "tokens": 0, "usage_complete": True, "observer": events.append}
        with patch("src.agent.read_response", side_effect=replies), patch("src.agent.run_tool_details", return_value=("2", True)):
            self.assertEqual(_run("算一下", 8, state, []), "2")
        kinds = [e["type"] for e in events]
        self.assertLess(kinds.index("tools_pending"), kinds.index("tool"))
        result = next(e for e in events if e["type"] == "tool")
        self.assertEqual(result["tool_call_id"], "call-1")
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
