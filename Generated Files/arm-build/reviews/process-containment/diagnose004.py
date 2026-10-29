"""Short diagnostic repetitions, not replacement tests or performance samples."""

import ctypes
from ctypes import wintypes as w
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import unittest
import uuid
from unittest.mock import patch

PROTOCOL = Path(__file__).resolve().parents[2] / "protocol"
sys.path.insert(0, str(PROTOCOL))
import owned_process as owned
import test_owned_process as tests

records = []
current = {}
original_alive = owned._Job.alive
original_spawn = owned.subprocess.Popen
api = owned._windows()
api.QueryFullProcessImageNameW.argtypes = [
    w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)
]
api.QueryFullProcessImageNameW.restype = w.BOOL


def describe(pid):
    handle = api.OpenProcess(0x101000, False, pid)
    if not handle:
        return {"pid": pid, "open_error": ctypes.get_last_error()}
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = w.DWORD(len(buffer))
        ok = api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
        return {
            "pid": pid, "image": buffer.value if ok else None,
            "wait_state": api.WaitForSingleObject(handle, 0),
        }
    finally:
        owned._checked(api.CloseHandle(handle))


def members(job):
    class Members(ctypes.Structure):
        _fields_ = [
            ("assigned", w.DWORD), ("listed", w.DWORD),
            ("pids", ctypes.c_size_t * 16),
        ]
    value = Members()
    owned._checked(api.QueryInformationJobObject(
        job.handle, 3, ctypes.byref(value), ctypes.sizeof(value), None
    ))
    return {
        "assigned": value.assigned,
        "members": [describe(pid) for pid in value.pids[:value.listed]],
    }


def alive(job):
    result = original_alive(job)
    observation = {"alive": result, "at": time.perf_counter()}
    if result:
        observation.update(members(job))
    current.setdefault("job_checks", []).append(observation)
    return result


def spawn(*args, **kwargs):
    process = original_spawn(*args, **kwargs)
    current.setdefault("supervisor_launches", []).append({
        "argv": args[0], **describe(process.pid)
    })
    return process


class Diagnostic(tests.OwnedTests):
    def run_helper(self, role, timeout=5):
        result = super().run_helper(role, timeout)
        current["receipt"] = asdict(result)
        current["target_markers"] = [
            int(path.read_text()) for path in self.root.glob("pid-*")
        ]
        return result


if __name__ == "__main__":
    relationship_only = sys.argv[1:] == ["--relationship-only"]
    if relationship_only:
        records = json.loads(
            Path(__file__).with_name("diagnose004.json").read_text()
        )["records"]
    for iteration in range(0 if relationship_only else 16):
        instrumented = iteration >= 8
        current = {"iteration": iteration, "instrumented": instrumented}
        result = unittest.TestResult()
        if instrumented:
            with (
                patch.object(owned._Job, "alive", alive),
                patch.object(owned.subprocess, "Popen", spawn),
            ):
                Diagnostic(
                    "test_normal_unfiltered_logs_and_separate_infrastructure"
                ).run(result)
        else:
            Diagnostic(
                "test_normal_unfiltered_logs_and_separate_infrastructure"
            ).run(result)
        current["test_failures"] = len(result.failures)
        current["test_errors"] = [message for _, message in result.errors]
        records.append(current)
    current = {"kind": "separate minimal relationship probe, not original test"}
    root = Path(__file__).parent / (".relationship-" + uuid.uuid4().hex)
    root.mkdir()
    try:
        target = (
            "import json,os,sys;"
            "print(json.dumps(dict(pid=os.getpid(),parent=os.getppid(),"
            "executable=sys.executable,base_prefix=sys.base_prefix)))"
        )
        with patch.object(owned.subprocess, "Popen", spawn):
            receipt = owned.run_owned(
                [tests.PYTHON, "-I", "-c", target], cwd=root,
                env=os.environ.copy(), stdout_path=root / "out",
                stderr_path=root / "err", timeout=5,
            )
        current["target"] = json.loads((root / "out").read_text())
        current["receipt"] = asdict(receipt)
    finally:
        shutil.rmtree(root)
    relationship = current
    output = {
        "diagnostic_only": True, "interpreter": sys.executable,
        "base_prefix": sys.base_prefix,
        "test_sha256": hashlib.sha256(
            (PROTOCOL / "test_owned_process.py").read_bytes()
        ).hexdigest(),
        "supervisor_sha256": hashlib.sha256(
            (PROTOCOL / "owned_process.py").read_bytes()
        ).hexdigest(),
        "records": records,
        "relationship_probe": relationship,
    }
    destination = Path(__file__).with_name("diagnose004.json")
    destination.write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))
