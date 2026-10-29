"""Bounded invocation ownership; POSIX commands must not detach from the group."""

import ctypes
import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

_WINDOWS = os.name == "nt"


@dataclass(frozen=True)
class Receipt:
    returncode: int | None
    timed_out: bool
    command_wall: float | None
    infrastructure_wall: float | None
    ownership_established: bool
    survivors: bool | None
    cleanup_complete: bool
    errors: tuple[str, ...]

    @property
    def succeeded(self):
        return (
            self.returncode == 0
            and not self.timed_out
            and self.ownership_established
            and self.survivors is False
            and self.cleanup_complete
            and not self.errors
        )


def _windows():
    from ctypes import wintypes as w

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        "OpenJobObjectW": ([w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
        "GetCurrentProcess": ([], w.HANDLE),
        "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
        "SetInformationJobObject": (
            [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL
        ),
        "QueryInformationJobObject": (
            [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p],
            w.BOOL,
        ),
        "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
    }
    for name, (args, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


def _checked(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


class _Job:
    def __init__(self, name):
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", w.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", w.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", w.DWORD),
                ("SchedulingClass", w.DWORD),
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", Basic),
                ("IoInfo", ctypes.c_ulonglong * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self.api = _windows()
        self.handle = _checked(self.api.CreateJobObjectW(None, name))
        try:
            limits = Extended()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            _checked(self.api.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ))
        except BaseException:
            self.close()
            raise

    def alive(self):
        from ctypes import wintypes as w

        class Accounting(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_longlong),
                ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", w.DWORD),
                ("TotalProcesses", w.DWORD),
                ("ActiveProcesses", w.DWORD),
                ("TotalTerminatedProcesses", w.DWORD),
            ]

        info = Accounting()
        _checked(self.api.QueryInformationJobObject(
            self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None
        ))
        return bool(info.ActiveProcesses)

    def kill(self):
        from ctypes import wintypes as w

        capacity, handles = 8, []
        try:
            while True:
                class Members(ctypes.Structure):
                    _fields_ = [
                        ("NumberOfAssignedProcesses", w.DWORD),
                        ("NumberOfProcessIdsInList", w.DWORD),
                        ("ProcessIdList", ctypes.c_size_t * capacity),
                    ]

                members = Members()
                queried = self.api.QueryInformationJobObject(
                    self.handle, 3, ctypes.byref(members), ctypes.sizeof(members), None
                )
                if queried and (
                    members.NumberOfProcessIdsInList == members.NumberOfAssignedProcesses
                ):
                    break
                if not queried and ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
                    _checked(False)
                capacity *= 2
                if capacity > 65536:
                    raise RuntimeError("Owned job process list exceeded bound")
            for pid in members.ProcessIdList[:members.NumberOfProcessIdsInList]:
                handle = self.api.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
                if handle:
                    handles.append(handle)
                elif ctypes.get_last_error() != 87:
                    _checked(False)
            _checked(self.api.TerminateJobObject(self.handle, 1))
            deadline = time.perf_counter() + 5
            for handle in handles:
                milliseconds = max(0, int((deadline - time.perf_counter()) * 1000))
                if self.api.WaitForSingleObject(handle, milliseconds) != 0:
                    raise RuntimeError("Owned process termination did not complete")
        finally:
            for handle in handles:
                _checked(self.api.CloseHandle(handle))

    def close(self):
        _checked(self.api.CloseHandle(self.handle))


def _group_alive(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _supervise():
    spec = json.load(sys.stdin)
    result = {"owned": False, "started": None, "returncode": None, "timed_out": False}
    try:
        if _WINDOWS:
            api = _windows()
            handle = _checked(api.OpenJobObjectW(1, False, spec["job"]))
            try:
                _checked(api.AssignProcessToJobObject(handle, api.GetCurrentProcess()))
            finally:
                _checked(api.CloseHandle(handle))
        result["owned"] = True
        with open(spec["stdout"], "wb") as out:
            same = spec["stdout"] == spec["stderr"]
            err = out if same else open(spec["stderr"], "wb")
            try:
                result["started"] = time.perf_counter()
                child = subprocess.Popen(spec["argv"], stdout=out, stderr=err)
                try:
                    remaining = spec["timeout"] - (
                        time.perf_counter() - result["started"]
                    )
                    result["returncode"] = child.wait(timeout=max(0, remaining))
                except subprocess.TimeoutExpired:
                    result["timed_out"] = True
            finally:
                if not same:
                    err.close()
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
    print(json.dumps(result), flush=True)


def run_owned(argv, *, cwd, env, stdout_path, stderr_path, timeout=120) -> Receipt:
    """Run a fixed non-detaching command; caller must stop sampling unless succeeded."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive and finite")
    clock = time.perf_counter()
    job = process = None
    data, errors = {}, []
    survivors = None
    clean = False
    try:
        name = "arm-owned-" + uuid.uuid4().hex
        job = _Job(name) if _WINDOWS else None
        spec = {
            "argv": [str(v) for v in argv],
            "stdout": str(Path(stdout_path).resolve()),
            "stderr": str(Path(stderr_path).resolve()),
            "timeout": timeout,
            "job": name,
        }
        interpreter = (
            str(Path(sys.base_prefix) / "python.exe")
            if _WINDOWS else sys.executable
        )
        process = subprocess.Popen(
            [interpreter, "-I", str(Path(__file__).resolve()), "--supervisor"],
            cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=not _WINDOWS,
        )
        output, diagnostic = process.communicate(json.dumps(spec), timeout=timeout + 10)
        data = json.loads(output)
        if "error" in data:
            errors.append(data["error"])
        if process.returncode or diagnostic or not data["owned"]:
            raise RuntimeError("Supervisor ownership/setup failed: " + diagnostic)
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
        if isinstance(error, subprocess.TimeoutExpired):
            data["timed_out"] = True
    finally:
        try:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                alive = job.alive if job else lambda: _group_alive(process.pid)
                survivors = alive()
                if survivors:
                    if job:
                        job.kill()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                deadline = time.perf_counter() + 5
                while alive() and time.perf_counter() < deadline:
                    time.sleep(0.01)
                clean = not alive()
                if not clean:
                    errors.append("Owned family did not drain before cleanup deadline")
        except Exception as error:
            errors.append(f"cleanup {type(error).__name__}: {error}")
        finally:
            if job:
                try:
                    job.close()
                except Exception as error:
                    clean = False
                    errors.append(f"close {type(error).__name__}: {error}")
            if process:
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
    ended = time.perf_counter()
    started = data.get("started")
    wall = ended - started if started is not None else None
    infrastructure = started - clock if started is not None else None
    if data and started is None:
        infrastructure = ended - clock
    return Receipt(
        data.get("returncode"), data.get("timed_out", False)
        or (wall is not None and wall > timeout), wall,
        infrastructure, data.get("owned", False),
        survivors, clean, tuple(errors),
    )


if __name__ == "__main__" and sys.argv[1:] == ["--supervisor"]:
    _supervise()
