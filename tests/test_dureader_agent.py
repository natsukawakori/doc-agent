import gzip
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rag
from src.tools.registry import schemas


class DuReaderAgentTest(unittest.TestCase):
    def test_registry_has_dureader_not_file_reader(self):
        tools = {x["function"]["name"] for x in schemas()}
        self.assertIn("search_docs", tools)
        self.assertNotIn("read_file", tools)

    def test_lookup_retrieves_exact_requested_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corpus.gz"
            with gzip.open(path, "wt", encoding="utf-8") as f:
                f.write("a\t甲中文\nb\t乙中文\n")
            with patch.object(rag, "CORPUS", path):
                self.assertEqual(rag.get_passages(["b"]), {"b": "乙中文"})
                with self.assertRaises(ValueError):
                    rag.get_passages(["missing"])

    def test_search_reranks_and_returns_sources(self):
        class FakeCross:
            def __init__(self, *args, **kwargs):
                pass

            def predict(self, pairs, **kwargs):
                self.pairs = pairs
                return [0.1, 0.9]

        candidates = [{"id": "a", "dense_score": 0.8, "ordinal": 0},
                      {"id": "b", "dense_score": 0.7, "ordinal": 1}]
        with patch.object(rag, "retrieve_many", return_value=([candidates], "cpu")), \
             patch.object(rag, "get_passages", return_value={"a": "甲", "b": "乙"}), \
             patch("sentence_transformers.CrossEncoder", FakeCross):
            found = rag.search("问题", top_k=2)
        self.assertEqual([x["source"] for x in found], ["DuReader:b", "DuReader:a"])
        self.assertEqual(found[0]["text"], "乙")

    def test_lookup_checks_index_manifest_and_result_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lookup, cache = root / "lookup", root / "cache"
            lookup.mkdir()
            cache.mkdir()
            lines = ["a\t甲\n".encode(), "b\t乙\n".encode()]
            (lookup / "passages.tsv").write_bytes(b"".join(lines))
            (lookup / "offsets.u64").write_bytes(struct.pack("<QQ", 0, len(lines[0])))
            meta = {"count": 2, "corpus_sha256": "c", "ids_sha256": "i", "text_bytes": sum(map(len, lines))}
            (lookup / "manifest.json").write_text(json.dumps(meta), encoding="utf8")
            (cache / "manifest.json").write_text(json.dumps(meta), encoding="utf8")
            with patch.object(rag, "LOOKUP", lookup), patch.object(rag, "CACHE", cache):
                self.assertEqual(rag.get_passages(["b", "a"], [1, 0]), {"b": "乙", "a": "甲"})
                with self.assertRaisesRegex(ValueError, "ID"):
                    rag.get_passages(["a"], [1])

    def test_multiple_queries_keep_their_own_rankings(self):
        class FakeCross:
            def __init__(self, *args, **kwargs):
                pass

            def predict(self, pairs, **kwargs):
                self.assert_pairs = pairs
                return [0.1, 0.9, 0.8, 0.2]

        rows = [[{"id": "a", "dense_score": 0.8, "ordinal": 0},
                 {"id": "b", "dense_score": 0.7, "ordinal": 1}],
                [{"id": "c", "dense_score": 0.8, "ordinal": 2},
                 {"id": "d", "dense_score": 0.7, "ordinal": 3}]]
        with patch.object(rag, "retrieve_many", return_value=(rows, "cpu")), \
             patch.object(rag, "get_passages", return_value={"a": "甲", "b": "乙", "c": "丙", "d": "丁"}), \
             patch("sentence_transformers.CrossEncoder", FakeCross):
            found = rag.search_many(["一", "二"], top_k=2)
        self.assertEqual([[x["source"] for x in row] for row in found],
                         [["DuReader:b", "DuReader:a"], ["DuReader:c", "DuReader:d"]])


if __name__ == "__main__":
    unittest.main()
