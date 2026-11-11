"""独立进程执行工具，让单次工具调用可以被超时终止。"""
import json
import sys
from contextlib import redirect_stdout
from src.tools.registry import execute

try:
    name, arguments = json.loads(sys.stdin.read())
    with redirect_stdout(sys.stderr):
        result = execute(name, arguments)
    print(json.dumps({"result": result}, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
