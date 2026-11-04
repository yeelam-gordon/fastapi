"""Private launch anchor, executed inside the unchanged guardian's owned job."""

import ctypes
import json
import subprocess
import sys
from pathlib import Path


def qpc():
    v = ctypes.c_longlong()
    ctypes.windll.kernel32.QueryPerformanceCounter(ctypes.byref(v))
    return v.value


def filetime():
    v = ctypes.c_ulonglong()
    ctypes.windll.kernel32.GetSystemTimePreciseAsFileTime(ctypes.byref(v))
    return v.value


def process_times(process):
    """Read only the launched process handle; CPU values use FILETIME units."""
    created, exited, kernel, user = (ctypes.c_ulonglong() for _ in range(4))
    api = ctypes.windll.kernel32.GetProcessTimes
    api.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
    if not api(
        int(process._handle), *map(ctypes.byref, (created, exited, kernel, user))
    ):
        raise ctypes.WinError()
    return created.value, exited.value, kernel.value, user.value


def completed_cpu(process, anchor):
    """Cumulative process CPU, not time in a selected window or I/O wait."""
    if process.poll() is None:
        raise ValueError("process_still_running")
    created, _, kernel, user = process_times(process)
    if created != anchor["creation_filetime"]:
        raise ValueError("native_creation_mismatch")
    return {"process_kernel_100ns": kernel, "process_user_100ns": user}


def spawn(command):
    before = qpc()
    process = subprocess.Popen(command)
    after = qpc()
    created, _, _, _ = process_times(process)
    anchor = {
        "pid": process.pid,
        "qpc_before": before,
        "qpc_after": after,
        "creation_filetime": created,
        "filetime_after": filetime(),
    }
    frequency = ctypes.c_longlong()
    if not ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(frequency)):
        raise ctypes.WinError()
    anchor["qpc_frequency"] = frequency.value
    return process, anchor


if __name__ == "__main__":
    destination, *command = sys.argv[1:]
    process, anchor = spawn(command)
    code = process.wait()
    anchor["qpc_end"] = qpc()
    anchor.update(completed_cpu(process, anchor))
    Path(destination).write_text(json.dumps(anchor), encoding="utf-8")
    sys.exit(code)
