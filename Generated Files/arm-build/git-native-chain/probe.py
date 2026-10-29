"""One local, read-only Git command; sample only a private Windows job's PIDs."""

import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

import psutil

OUT = Path(__file__).resolve().parent
ROOT = Path(r"Q:\fastapi\Generated Files\arm-build")
CI = ROOT / r"diagnostics\analysis-runs\40859922266\artifacts\arm-analysis-windows\evidence\upload\report.json"
TRACE = ROOT / r"diagnostics\.local\git-trace2-13417175dd1a488fa2895ef1d60ef830\events.jsonl"
SOURCE = Path(r"Q:\fastapi\Generated Files\worktrees\source-fastapi")
k = C.WinDLL("kernel32", use_last_error=True)
nt = C.WinDLL("ntdll")
k.CreateJobObjectW.argtypes = [C.c_void_p, W.LPCWSTR]
k.CreateJobObjectW.restype = W.HANDLE
k.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
k.QueryInformationJobObject.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p]
k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k.OpenProcess.restype = W.HANDLE
k.CloseHandle.argtypes = [W.HANDLE]
k.IsWow64Process2.argtypes = [W.HANDLE, C.POINTER(W.WORD), C.POINTER(W.WORD)]
k.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
k.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
nt.NtResumeProcess.argtypes = [W.HANDLE]
nt.NtResumeProcess.restype = W.LONG
nt.NtQueryInformationProcess.argtypes = [W.HANDLE, W.ULONG, C.c_void_p, W.ULONG, C.c_void_p]
nt.NtQueryInformationProcess.restype = W.LONG


class BasicInfo(C.Structure):
    _fields_ = [
        ("reserved1", C.c_void_p),
        ("peb", C.c_void_p),
        ("reserved2", C.c_void_p * 2),
        ("pid", C.c_size_t),
        ("parent_pid", C.c_size_t),
    ]


def unavailable(reason):
    return {"status": "unavailable", "reason": reason, "value": None}


def identity(path):
    try:
        data = Path(path).read_bytes()
        machine = None
        if data[:2] == b"MZ":
            offset = struct.unpack_from("<I", data, 0x3C)[0]
            if data[offset:offset + 4] == b"PE\0\0":
                machine = f"0x{struct.unpack_from('<H', data, offset + 4)[0]:04x}"
        return {
            "path": str(path),
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "pe_machine": machine,
            "header_is_execution_proof": False,
        }
    except OSError as exc:
        return unavailable(type(exc).__name__)


def job_pids(job):
    # No system process enumeration: class 3 returns only this private job.
    buffer = C.create_string_buffer(8 + 4096 * C.sizeof(C.c_size_t))
    if not k.QueryInformationJobObject(job, 3, buffer, len(buffer), None):
        raise C.WinError(C.get_last_error())
    count = struct.unpack_from("<I", buffer, 4)[0]
    return list((C.c_size_t * count).from_buffer(buffer, 8))


def sample(pid):
    result = {"pid": pid}
    handle = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        result["query"] = unavailable(f"OpenProcess winerror={C.get_last_error()}")
        return result
    try:
        times = [W.FILETIME() for _ in range(4)]
        if k.GetProcessTimes(handle, *(C.byref(t) for t in times)):
            result["creation_time_100ns_since_1601"] = (
                times[0].dwHighDateTime << 32
            ) | times[0].dwLowDateTime
        else:
            result["creation_time"] = unavailable(f"winerror={C.get_last_error()}")
        info = BasicInfo()
        status = nt.NtQueryInformationProcess(handle, 0, C.byref(info), C.sizeof(info), None)
        result["parent_pid"] = info.parent_pid if status == 0 else unavailable(f"NTSTATUS={status}")
        process_machine, native_machine = W.WORD(), W.WORD()
        if k.IsWow64Process2(handle, C.byref(process_machine), C.byref(native_machine)):
            result["IsWow64Process2"] = {
                "status": "measured",
                "process_machine": f"0x{process_machine.value:04x}",
                "native_machine": f"0x{native_machine.value:04x}",
                "source": "live process query-limited handle",
            }
        else:
            result["IsWow64Process2"] = unavailable(f"winerror={C.get_last_error()}")
        try:
            result["exe"] = psutil.Process(pid).exe()
        except psutil.Error as exc:
            result["exe"] = unavailable(type(exc).__name__)
    finally:
        k.CloseHandle(handle)
    return result


def main():
    ci = json.loads(CI.read_text(encoding="utf-8"))["platform_inventory"]["tools"]["git"]
    (OUT / "ci-git-receipt.json").write_text(json.dumps(ci, indent=2) + "\n", encoding="utf-8")
    trace_rows = [json.loads(line) for line in TRACE.read_text(encoding="utf-8").splitlines()]
    # Retain only public Git version and child records, not ancestry, argv or environment.
    public_trace = [
        {key: row[key] for key in ("event", "time", "exe", "child_id", "pid", "code", "t_rel") if key in row}
        for row in trace_rows if row["event"] in ("version", "child_exit")
    ]
    (OUT / "existing-trace-public-extract.json").write_text(
        json.dumps(public_trace, indent=2) + "\n", encoding="utf-8"
    )
    command = [shutil.which("git"), "-C", str(SOURCE), "submodule", "foreach", "--recursive", "exit 0"]
    if not command[0]:
        raise RuntimeError("git not found")
    job = k.CreateJobObjectW(None, None)
    if not job:
        raise C.WinError(C.get_last_error())
    records, errors = {}, []
    started = time.monotonic()
    timed_out = False
    with (OUT / "stdout.txt").open("wb") as stdout, (OUT / "stderr.txt").open("wb") as stderr:
        child = subprocess.Popen(
            command, stdout=stdout, stderr=stderr,
            creationflags=0x4,  # CREATE_SUSPENDED: assign before any child can escape sampling scope.
        )
        try:
            if not k.AssignProcessToJobObject(job, int(child._handle)):
                raise C.WinError(C.get_last_error())
            if nt.NtResumeProcess(int(child._handle)) != 0:
                raise RuntimeError("NtResumeProcess failed")
            while True:
                pids = job_pids(job)
                now = time.monotonic() - started
                for pid in pids:
                    if pid not in records:
                        records[pid] = sample(pid)
                        records[pid]["first_seen_seconds"] = now
                    records[pid]["last_seen_seconds"] = now
                if not pids:
                    break
                if now >= 15:
                    timed_out = True
                    # Terminate only handles obtained from our private job's PID list.
                    for pid in pids:
                        handle = k.OpenProcess(0x1001, False, pid)
                        if handle:
                            try:
                                current = sample(pid)
                                expected = records[pid].get("creation_time_100ns_since_1601")
                                if expected is not None and current.get("creation_time_100ns_since_1601") == expected:
                                    k.TerminateProcess(handle, 124)
                            finally:
                                k.CloseHandle(handle)
                    break
                time.sleep(0.005)
            child.wait(timeout=2)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            # Popen retains the original owned root handle, never a name-based kill.
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=2)
        finally:
            k.CloseHandle(job)
    elapsed = time.monotonic() - started
    images = {
        row["exe"]: identity(row["exe"])
        for row in records.values() if isinstance(row.get("exe"), str)
    }
    ci_images = [ci["binary"]] + [item["identity"] for item in ci["helpers"]["candidates"]]
    comparisons = []
    for local in images.values():
        comparisons.append({
            "local_path": local.get("path"),
            "local_sha256": local.get("sha256"),
            "ci_same_hash_paths": [
                item["path"] for item in ci_images
                if item.get("sha256") and item["sha256"] == local.get("sha256")
            ],
            "ci_same_path": [
                {"path": item["path"], "sha256": item.get("sha256"),
                 "hash_equal": item.get("sha256") == local.get("sha256")}
                for item in ci_images
                if item.get("path", "").lower() == local.get("path", "").lower()
            ],
        })
    report = {
        "command": command, "scope": "one private job; owned Git descendants only",
        "sampling": "partial 5ms polling, not a complete process or CPU-family trace",
        "python": {"version": sys.version, "executable": sys.executable, "psutil_version": psutil.__version__,
                   "binary": identity(sys.executable)},
        "ci_report_path": str(CI), "ci_report_sha256": hashlib.sha256(CI.read_bytes()).hexdigest(),
        "existing_trace_sha256": hashlib.sha256(TRACE.read_bytes()).hexdigest(),
        "local_version_from_existing_trace_only": [r["exe"] for r in public_trace if "exe" in r],
        "ci_version": ci["version"],
        "elapsed_seconds_diagnostic_only_shared_host": elapsed,
        "exit_code": child.returncode, "timed_out": timed_out, "errors": errors,
        "processes": list(records.values()), "unique_images": list(images.values()),
        "ci_comparisons": comparisons,
    }
    (OUT / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if child.returncode == 0 and not errors and not timed_out else 1


if __name__ == "__main__":
    raise SystemExit(main())
