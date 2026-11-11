"""仅通过 DuReader 段落 ID 读取公开语料，不接受本机路径。"""
import re
from pathlib import Path

from src import rag


def find_ordinal(passage_id):
    if not isinstance(passage_id, str) or not re.fullmatch(r"[0-9a-f]{32}", passage_id):
        raise ValueError("段落 ID 必须是 32 位小写十六进制字符")
    path = rag.CACHE / "ids.bin"
    target = passage_id.encode("ascii")
    base = 0
    with path.open("rb") as f:
        while block := f.read(32 * 32768):
            pos = block.find(target)
            while pos != -1:
                if pos % 32 == 0:
                    return (base + pos) // 32
                pos = block.find(target, pos + 1)
            base += len(block)
    raise ValueError("DuReader 中没有该段落 ID")


def read_passage(passage_id, max_chars=16000):
    if not 1 <= max_chars <= 16000:
        raise ValueError("max_chars 必须在 1 到 16000 之间")
    ordinal = find_ordinal(passage_id)
    text = rag.get_passages([passage_id], [ordinal])[passage_id]
    return {"source": "DuReader:" + passage_id, "text": text[:max_chars],
            "truncated": len(text) > max_chars}
