import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.passage import find_ordinal, read_passage


class PassageTest(unittest.TestCase):
    def test_id_validation_and_aligned_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            first, second = "a" * 32, "b" * 32
            (cache / "ids.bin").write_bytes((first * 32768 + second).encode("ascii"))
            with patch("src.passage.rag.CACHE", cache):
                self.assertEqual(find_ordinal(second), 32768)
                with self.assertRaises(ValueError):
                    find_ordinal("../secret")
                with self.assertRaises(ValueError):
                    find_ordinal("c" * 32)

    def test_read_limits_and_marks_truncation(self):
        with patch("src.passage.find_ordinal", return_value=7), \
             patch("src.passage.rag.get_passages", return_value={"a" * 32: "abcdefgh"}):
            result = read_passage("a" * 32, max_chars=4)
        self.assertEqual(result["text"], "abcd")
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
