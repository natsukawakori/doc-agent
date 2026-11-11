import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from src.faiss_scan import scan


class FaissScanTest(unittest.TestCase):
    def test_exact_search_keeps_queries_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vectors.bin"
            vectors = np.zeros((3, 512), dtype="<f4")
            vectors[0, 0], vectors[1, 1], vectors[2, 0] = 1.0, 1.0, 0.5
            path.write_bytes(vectors.tobytes())
            queries = np.zeros((2, 512), dtype="float32")
            queries[0, 0], queries[1, 1] = 1, 1
            with patch("src.faiss_scan.available_memory", return_value=8 * 1024**3):
                ids, scores = scan(queries, path, "<f4", 4, 3, 2)
            self.assertEqual(ids[0], [0, 2])
            self.assertEqual(ids[1][0], 1)
            self.assertEqual(scores[0], [1.0, 0.5])


if __name__ == "__main__":
    unittest.main()
