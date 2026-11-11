import unittest
from eval.report import report
from eval.quality_metrics import summarize


class ReportTest(unittest.TestCase):
    def test_empty_metrics_are_not_misrepresented(self):
        text = report(summarize([], []))
        self.assertIn('未评估', text)
        self.assertNotIn('0.00%', text)
