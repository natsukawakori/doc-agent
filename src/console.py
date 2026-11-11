"""终端编码受限时不让日志输出中断 Agent 的工作。"""
import builtins
import sys


def safe_print(*args, **kwargs):
    stream = kwargs.get("file") or sys.stdout
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        try:
            safe = [str(x).encode(encoding, errors="backslashreplace").decode(encoding) for x in args]
            builtins.print(*safe, **kwargs)
        except (LookupError, UnicodeError, OSError, ValueError):
            pass
    except (OSError, ValueError):
        pass
