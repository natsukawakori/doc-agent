"""控制 GPU 扫描时的温度，并在内存不足时释放自身工作集后等待。"""
import ctypes
import gc
import subprocess
import time


class MemoryStatus(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong)] + [
        (name, ctypes.c_ulonglong) for name in ("total_phys", "avail_phys", "total_page",
                                               "avail_page", "total_virtual", "avail_virtual", "avail_extended")]


def available_memory():
    state = MemoryStatus()
    state.length = ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise ctypes.WinError()
    return state.avail_phys


def trim_own_working_set():
    """仅处理当前进程的可分页工作集；不终止或修改其他程序。"""
    gc.collect()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.K32EmptyWorkingSet.argtypes = [ctypes.c_void_p]
    kernel.K32EmptyWorkingSet.restype = ctypes.c_int
    if not kernel.K32EmptyWorkingSet(kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())


def gpu_temperature():
    result = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=10, check=True)
    return float(result.stdout.splitlines()[0].strip())


def wait_for_memory(memory_min_gib=1.0, resume_gib=1.25):
    available = available_memory() / 1024**3
    if available >= memory_min_gib:
        return
    print(f"系统可用内存 {available:.2f} GiB；检查点已保存，清理本进程工作集并等待。", flush=True)
    try:
        trim_own_working_set()
    except OSError as exc:
        print(f"本进程工作集回收失败：{exc}；仍将等待可用内存恢复。", flush=True)
    waits = 0
    while (available := available_memory() / 1024**3) < resume_gib:
        time.sleep(10)
        waits += 1
        if waits % 6 == 0:
            print(f"等待内存恢复：当前 {available:.2f} GiB，目标 {resume_gib:.2f} GiB。", flush=True)
    print(f"系统可用内存已恢复至 {available:.2f} GiB，继续运行。", flush=True)


def pace(processed, seconds, temp_limit=83, memory_min_gib=1.0):
    if seconds:
        time.sleep(seconds)
    if processed % 1024:
        return
    if processed % 4096 == 0:
        wait_for_memory(memory_min_gib=memory_min_gib)
    temp = gpu_temperature()
    if temp >= temp_limit:
        print(f"显卡 {temp:.1f}°C，暂缓运行等待降至 {temp_limit - 5}°C", flush=True)
        while temp > temp_limit - 5:
            time.sleep(10)
            temp = gpu_temperature()
        print(f"显卡已降至 {temp:.1f}°C，继续运行", flush=True)
