"""线程之间共享的协作式取消与任务期限，不强杀同步调用。"""
import math
import os
import threading
import time


class ExecutionStopped(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class ExecutionControl:
    def __init__(self, timeout_seconds=900, clock=time.monotonic):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError('任务期限须为大于零的有限秒数')
        self._clock = clock
        self._deadline = clock() + timeout_seconds
        self._cancelled = threading.Event()

    @classmethod
    def from_env(cls):
        return cls(float(os.getenv('DOC_AGENT_TASK_TIMEOUT_SECONDS', '900')))

    def cancel(self):
        self._cancelled.set()

    def check(self):
        if self._cancelled.is_set():
            raise ExecutionStopped('cancelled', '连接已断开，任务在可控边界停止。')
        if self._clock() >= self._deadline:
            raise ExecutionStopped('timeout', '任务已达到时间限制，在可控边界停止；已开始的调用可能仍需等待。')
