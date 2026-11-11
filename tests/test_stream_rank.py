import unittest
import torch
from eval.stream_rank import StreamingTopK


class StreamRankTest(unittest.TestCase):
    def test_global_top_k_across_batches_and_resume(self):
        queries = torch.tensor([[1., 0.], [0., 1.]])
        ranker = StreamingTopK(queries, k=2)
        ranker.update(torch.tensor([[.2, .7], [.8, .1]]), ['a', 'b'], 0)
        restored = StreamingTopK(queries, k=2, state=ranker.state())
        restored.update(torch.tensor([[.9, .0], [.1, .95]]), ['c', 'd'], 2)
        result = restored.results()
        self.assertEqual([x['id'] for x in result[0]], ['c', 'b'])
        self.assertEqual([x['id'] for x in result[1]], ['d', 'a'])

    def test_reject_bad_dimensions_and_state(self):
        ranker = StreamingTopK(torch.tensor([[1., 0.]]), k=2)
        with self.assertRaises(ValueError):
            ranker.update(torch.tensor([[1., 2., 3.]]), ['x'], 0)
        with self.assertRaises(ValueError):
            StreamingTopK(torch.tensor([[1., 0.]]), state=[])


if __name__ == '__main__':
    unittest.main()
