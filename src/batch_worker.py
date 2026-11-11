"""执行一组文档搜索；输出 JSON，过程日志发送到 stderr。"""
import json
import sys
from contextlib import redirect_stdout

try:
    queries = json.loads(sys.stdin.read())
    with redirect_stdout(sys.stderr):
        from src.rag import search_many
        results = search_many(queries)
    print(json.dumps(results, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
