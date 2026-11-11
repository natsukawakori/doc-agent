"""轻量进程内会话，限制同一时间只运行一个 Agent。"""
import secrets
import threading

sessions = {}
busy = threading.Lock()


def create_session():
    if len(sessions) >= 128:
        raise RuntimeError("会话数量已达上限，请重启本地服务")
    key = secrets.token_urlsafe(24)
    sessions[key] = []
    return key
