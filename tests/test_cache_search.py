import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import torch
from eval.cache_search import search_vectors


class CachedSearchTest(unittest.TestCase):
    def test_reuses_saved_vectors_without_document_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            np.array([[.1, .9], [.9, .1], [.8, .2]], dtype='<f4').tofile(root/'vectors.f32')
            (root/'ids.bin').write_bytes(('a'*32+'b'*32+'c'*32).encode('ascii'))
            manifest = {'count':3, 'dimension':2, 'vectors_file':'vectors.f32', 'ids_file':'ids.bin'}
            (root/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            result = search_vectors(root, torch.tensor([[1., 0.]]), 2)
            self.assertEqual([x['id'] for x in result[0]], ['b'*32, 'c'*32])
            with self.assertRaises(ValueError):
                search_vectors(root, torch.tensor([[1., 0.]]), 4)


if __name__ == '__main__':
    unittest.main()
