"""Bounded owned-job diagnostic; no system process enumeration."""

import ctypes
import json
import os
import sys
import uuid
from pathlib import Path
from ctypes import wintypes as w

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import owned_process as owned


root = Path(__file__).parent / (".liveness-" + uuid.uuid4().hex)
root.mkdir()
original = owned._Job.alive
observations = []


def observe(job):
    alive = original(job)
    if alive:
        class Members(ctypes.Structure):
            _fields_ = [
                ("assigned", w.DWORD), ("listed", w.DWORD),
                ("pids", ctypes.c_size_t * 32),
            ]
        members = Members()
        owned._checked(job.api.QueryInformationJobObject(
            job.handle, 3, ctypes.byref(members), ctypes.sizeof(members), None
        ))
        statuses = []
        for pid in members.pids[:members.listed]:
            handle = job.api.OpenProcess(0x100000, False, pid)
            if handle:
                try:
                    state = job.api.WaitForSingleObject(handle, 0)
                    statuses.append({"pid": pid, "wait": state})
                finally:
                    owned._checked(job.api.CloseHandle(handle))
            else:
                statuses.append({"pid": pid, "open_error": ctypes.get_last_error()})
        observations.append({"assigned": members.assigned, "listed": members.listed,
                             "statuses": statuses})
    return alive


owned._Job.alive = observe
records = []
spawn = owned.subprocess.Popen
supervisor = None


def track_spawn(*args, **kwargs):
    global supervisor
    process = spawn(*args, **kwargs)
    supervisor = process.pid
    return process


owned.subprocess.Popen = track_spawn
try:
    for index in range(16):
        begin = len(observations)
        out, err = root / f"{index}.out", root / f"{index}.err"
        result = owned.run_owned(
            [str(Path(sys.base_prefix) / "python.exe"), "-I",
             str(Path(__file__).resolve().parents[1] / "test_owned_process.py"),
             "--helper", "normal", str(root.resolve())],
            cwd=root, env=os.environ.copy(), stdout_path=out, stderr_path=err,
            timeout=5,
        )
        records.append({"index": index, "succeeded": result.succeeded,
                        "survivors": result.survivors, "errors": result.errors,
                        "cleanup_complete": result.cleanup_complete,
                        "supervisor": supervisor,
                        "stdout": out.read_text(),
                        "observations": observations[begin:]})
        out.unlink()
        err.unlink()
finally:
    for path in root.glob("pid-*"):
        path.unlink()
    root.rmdir()
(Path(__file__).parent / "managed-liveness-before.json").write_text(
    json.dumps(records, indent=2) + "\n"
)
print(json.dumps(records, indent=2))
