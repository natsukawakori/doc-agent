"""运行隔离工具并在超时后清理进程树。"""
import os
import signal
import subprocess


class CleanupUncertainError(subprocess.TimeoutExpired):
    """超时后无法确认整个进程树已结束；调用方不应立即重试。"""


def run_worker(command, *, payload, cwd, timeout, env):
    options = {'stdin': subprocess.PIPE, 'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE,
               'text': True, 'encoding': 'utf-8', 'cwd': cwd, 'env': env}
    if os.name == 'nt':
        options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options['start_new_session'] = True
    proc = subprocess.Popen(command, **options)
    try:
        stdout, stderr = proc.communicate(payload, timeout=timeout)
        return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        uncertain = False
        if proc.poll() is None:
            if os.name == 'nt':
                try:
                    result = subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                            capture_output=True, timeout=10, check=False)
                    uncertain = result.returncode != 0
                except (OSError, subprocess.TimeoutExpired):
                    uncertain = True
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    uncertain = True
            if proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    uncertain = True
        else:
            # 父进程已退出但管道未关闭，可能有子进程仍持有管道。
            uncertain = True
        # 避免子进程意外保留管道时无限等待。
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            uncertain = True
            if proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
        if uncertain:
            raise CleanupUncertainError(command, timeout)
        raise subprocess.TimeoutExpired(command, timeout)
