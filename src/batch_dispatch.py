"""合并同一模型消息中可安全批处理的文档搜索。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from src.process_runner import run_worker, CleanupUncertainError

PROJECT = Path(__file__).resolve().parent.parent


def run_with_cache(calls, remaining, local_cache, *, scan):
    """全命中时复用；有缺失时仍对整个批次扫描，保持结果一致。"""
    keys = None
    if os.getenv('DOC_AGENT_SEARCH_CACHE', '0') == '1':
        started = time.perf_counter()
        try:
            from src.search_cache import prepare_batch
            prepared = prepare_batch(calls, remaining, local_cache)
            if prepared:
                keys, values = prepared
                if all(value is not None for value in values):
                    return (values, time.perf_counter() - started), True
        except Exception:
            keys = None
    result = scan(calls, remaining, local_cache)
    if result is not None and keys:
        try:
            from src.search_cache import put
            for key, value in zip(keys, result[0]):
                put(key, value)
        except Exception:
            pass
    return result, False


def run_batch(calls, remaining, cache):
    if not 2 <= len(calls) <= min(8, remaining):
        return None
    queries, keys = [], []
    try:
        for call in calls:
            function = call["function"]
            args = json.loads(function["arguments"])
            if (function["name"] != "search_docs" or not isinstance(args, dict) or
                    set(args) != {"query"} or not isinstance(args["query"], str) or not args["query"].strip()):
                return None
            key = json.dumps(args, ensure_ascii=False, sort_keys=True)
            if key in cache or key in keys:
                return None
            queries.append(args["query"])
            keys.append(key)
    except (ValueError, TypeError, KeyError):
        return None
    gpu_python = PROJECT / ".venv-gpu" / "Scripts" / "python.exe"
    executable = str(gpu_python) if gpu_python.exists() else sys.executable
    started = time.perf_counter()
    print(f"[工具] 开始合并 {len(queries)} 个文档查询", flush=True)
    try:
        proc = run_worker([executable, "-m", "src.batch_worker"], payload=json.dumps(queries, ensure_ascii=False),
                              cwd=PROJECT, timeout=300,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if proc.returncode:
            return None
        data = json.loads(proc.stdout)
        if not isinstance(data, list) or len(data) != len(queries) or any(not isinstance(x, list) for x in data):
            return None
    except CleanupUncertainError:
        raise  # 不能在可能遗留旧进程时退回逐条搜索
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    results = [json.dumps(row, ensure_ascii=False) for row in data]
    return results, time.perf_counter() - started
