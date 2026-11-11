import unittest
from eval.benchmark_dureader import evaluate_ranking


class MetricsTest(unittest.TestCase):
    def test_one_of_two_relevant_at_second_position(self):
        result = evaluate_ranking(['x', 'a', 'y'], {'a', 'b'})
        self.assertEqual(result['hit1'], 0)
        self.assertEqual(result['hit5'], 1)
        self.assertEqual(result['recall10'], .5)
        self.assertEqual(result['mrr10'], .5)

    def test_miss_and_invalid_label(self):
        self.assertEqual(evaluate_ranking(['x'], {'a'})['mrr10'], 0)
        with self.assertRaises(ValueError):
            evaluate_ranking(['x'], set())


if __name__ == '__main__':
    unittest.main()
