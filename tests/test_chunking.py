import tempfile
import unittest
from pathlib import Path
from src.chunking import chunks


class ChunkingTest(unittest.TestCase):
    def test_heading_and_code_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / "doc.md"
            file.write_text("# 第一章\n介绍\n## 小节\n正文\n```python\n# 注释\n```\n尾声", encoding="utf-8")
            result = chunks(file, root)
            self.assertEqual(result[0]["heading"], "第一章")
            self.assertEqual(result[1]["heading"], "第一章 > 小节")
            self.assertIn("# 注释", result[1]["text"])
            self.assertEqual(result[1]["source"], "doc.md")

    def test_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / "doc.md"
            file.write_text("# 标题\nabcdefghijk", encoding="utf-8")
            result = chunks(file, root, limit=5, overlap=2)
            self.assertEqual([item["text"] for item in result], ["abcde", "defgh", "ghijk"])


if __name__ == "__main__":
    unittest.main()
