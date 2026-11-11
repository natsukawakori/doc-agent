import unittest
import io
from contextlib import redirect_stdout
from eval.acceptance_m3 import print_table, scores


class AcceptanceScoreTest(unittest.TestCase):
    def test_aggregates_hits_steps_latency_and_missing_usage(self):
        rows = [
            {"hit1": True, "hit3": True, "steps": 1, "seconds": 2, "failures": 0, "answer": "A", "tokens": 10},
            {"hit1": False, "hit3": True, "steps": 2, "seconds": 4, "failures": 1, "answer": "B", "tokens": None},
        ]
        out = scores(rows)
        self.assertEqual(out["hit@1"], 0.5)
        self.assertEqual(out["hit@3"], 1.0)
        self.assertEqual(out["avg_steps"], 1.5)
        self.assertEqual(out["avg_latency_seconds"], 3)
        self.assertEqual(out["tool_failure_rate"], 1/3)
        self.assertEqual(out["tokens_known"], 1)
        self.assertEqual(out["total_tokens_when_known"], 10)

    def test_table_displays_each_case(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            print_table([{"id": "x", "hit1": True, "hit3": True, "steps": 1,
                          "failures": 0, "seconds": 2.0, "tokens": 3}])
        self.assertIn("x | 1 | 1 | 1 | 0 | 2.00 | 3", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
