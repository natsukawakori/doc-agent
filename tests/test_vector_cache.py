import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch
from eval.vector_cache import VectorCache
from eval.full_guard import pace


class CacheTest(unittest.TestCase):
    def test_resume_overwrites_uncheckpointed_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c, d = ('a'*32, 'b'*32, 'c'*32, 'd'*32)
            cache = VectorCache(tmp, 2, 0)
            cache.append([a, b], torch.tensor([[1., 2.], [3., 4.]]))
            cache.sync()
            cache.append([c], torch.tensor([[5., 6.]]))
            cache.vectors.close()
            cache.ids.close()
            resumed = VectorCache(tmp, 2, 2, resume=True)
            resumed.append([d], torch.tensor([[7., 8.]]))
            resumed.finish(3)
            ids = (Path(tmp)/'ids.bin').read_bytes()
            self.assertEqual(ids, (a+b+d).encode('ascii'))
            matrix = np.fromfile(Path(tmp)/'vectors.f32', dtype='<f4').reshape(-1, 2)
            np.testing.assert_array_equal(matrix, [[1., 2.], [3., 4.], [7., 8.]])

    def test_resume_at_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = VectorCache(tmp, 2, 0)
            cache.sync()
            cache.vectors.close()
            cache.ids.close()
            resumed = VectorCache(tmp, 2, 0, resume=True)
            resumed.finish(0)

    def test_invalid_identifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = VectorCache(tmp, 2, 0)
            try:
                with self.assertRaises(ValueError):
                    cache.append(['invalid'], torch.tensor([[1., 2.]]))
            finally:
                cache.vectors.close()
                cache.ids.close()


class GuardTest(unittest.TestCase):
    @patch('eval.full_guard.time.sleep')
    @patch('eval.full_guard.gpu_temperature', side_effect=[84., 79., 78.])
    @patch('eval.full_guard.available_memory', return_value=2*1024**3)
    def test_cools_down_before_continue(self, mem, temp, sleep):
        with patch('builtins.print'):
            pace(4096, .5)
        self.assertEqual(temp.call_count, 3)
        self.assertEqual(sleep.call_count, 3)

    @patch('eval.full_guard.gpu_temperature', return_value=70.)
    @patch('eval.full_guard.trim_own_working_set')
    @patch('eval.full_guard.available_memory', side_effect=[512*1024**2, 768*1024**2, int(1.5*1024**3)])
    @patch('eval.full_guard.time.sleep')
    def test_low_memory_waits_until_recovered(self, sleep, mem, trim, temp):
        with patch('builtins.print'):
            pace(4096, 0)
        trim.assert_called_once()
        sleep.assert_called_once_with(10)
        temp.assert_called_once()


if __name__ == '__main__':
    unittest.main()
