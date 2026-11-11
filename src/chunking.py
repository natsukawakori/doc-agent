"""按 Markdown 标题切块，保留标题路径与源文件。"""
import re
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def chunks(path, root, limit=220, overlap=40):
    path, root = Path(path), Path(root)
    if limit <= 0 or overlap < 0 or overlap >= limit:
        raise ValueError("切块长度必须大于重叠长度")
    headings, body, output = [], [], []
    def flush():
        text = "\n".join(body).strip()
        if text:
            start = 0
            while start < len(text):
                part = text[start:start + limit]
                output.append({"source": path.relative_to(root).as_posix(),
                               "heading": " > ".join(h for _, h in headings),
                               "text": part})
                if start + limit >= len(text):
                    break
                start += limit - overlap
        body.clear()
    fence = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match_fence = FENCE.match(line)
        if match_fence:
            marker = match_fence.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            body.append(line)
            continue
        match = HEADING.match(line) if fence is None else None
        if match:
            flush()
            level, title = len(match.group(1)), match.group(2)
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, title))
        else:
            body.append(line)
    flush()
    return output


def load_corpus(root):
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"找不到文档目录：{root}")
    result = []
    for path in sorted(root.rglob("*.md")):
        if "images" not in path.relative_to(root).parts:
            result.extend(chunks(path, root))
    return result

