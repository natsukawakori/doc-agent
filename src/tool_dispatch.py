"""工具进程执行、受控重试与错误格式。"""
import json
import os
import subprocess
import sys
from pathlib import Path
from src.process_runner import run_worker, CleanupUncertainError
from src.tools.registry import limits
from src.console import safe_print as print

PROJECT = Path(__file__).resolve().parent.parent


class ToolResult(str):
    def __new__(cls, value, attempts):
        result = super().__new__(cls, value)
        result.attempts = attempts
        return result


def tool_error_message(name, result):
    """给模型的失败回填使用明确结构；保留原始工具事件供排查。"""
    text = str(result)
    if '进程树清理状态不确定' in text:
        kind, hint = 'cleanup_uncertain', '不要重试工具，请检查系统中的残留进程。'
    elif '参数' in text or 'ValueError' in text or '未知工具' in text:
        kind, hint = 'invalid_arguments', '检查工具名称和参数，不要重复相同错误。'
    elif '超时' in text or 'Timeout' in text:
        kind, hint = 'timeout', '可以调整策略或说明工具暂时不可用。'
    elif 'URLError' in text or 'ConnectionError' in text:
        kind, hint = 'network_error', '网络暂不可用，可稍后重试或说明限制。'
    else:
        kind, hint = 'tool_failure', '检查失败原因，必要时换策略或说明限制。'
    return json.dumps({'tool': name, 'error_type': kind, 'message': text[:500], 'hint': hint}, ensure_ascii=False)


def run_tool_details(name, arguments):
    attempts = 0
    try:
        payload = json.dumps([name, arguments], ensure_ascii=False)
        gpu_python = PROJECT / ".venv-gpu" / "Scripts" / "python.exe"
        executable = str(gpu_python) if name == "search_docs" and gpu_python.exists() else sys.executable
        timeout, retries = limits(name)
        for attempt in range(retries + 1):
            attempts += 1
            try:
                process = run_worker(
                    [executable, "-m", "src.tool_worker"], payload=payload, cwd=PROJECT,
                    timeout=timeout, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
            except CleanupUncertainError:
                return ToolResult('工具超时且进程树清理状态不确定，已停止重试。', attempts), False
            except subprocess.TimeoutExpired:
                if attempt < retries:
                    print(f'[工具] {name} 超时，重试一次。', flush=True)
                    continue
                return ToolResult(f"工具执行超时（已重试 {attempt} 次）", attempts), False
            if process.returncode:
                return ToolResult(f"工具进程失败：{process.stderr[:500]}", attempts), False
            data = json.loads(process.stdout)
            error = str(data.get('error', ''))
            if name == 'web_fetch' and error.startswith(('URLError:', 'TimeoutError:')) and attempt < retries:
                print(f'[工具] {name} 网络错误，重试一次。', flush=True)
                continue
            return ToolResult(str(data.get("result", data.get("error", "工具无输出"))), attempts), "error" not in data and "result" in data
    except (ValueError, OSError) as exc:
        return ToolResult(f"工具执行失败：{exc}", attempts), False


