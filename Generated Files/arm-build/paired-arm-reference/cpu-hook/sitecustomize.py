"""Exit-only SELF CPU receipt for the explicitly instrumented LF reference."""

import atexit
import json
import math
import os
import sys

_RECEIPT_DIR = os.environ.get("HOBL_CPU_RECEIPT_DIR")


def cpu_record(pid, ppid, argv, user, system):
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or not isinstance(ppid, int)
        or isinstance(ppid, bool)
        or ppid < 0
    ):
        raise ValueError("Unknown or invalid Python PID/PPID")
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        raise ValueError("Unknown Python orig_argv")
    for counter in (user, system):
        if (
            not isinstance(counter, (int, float))
            or isinstance(counter, bool)
            or not math.isfinite(counter)
            or counter < 0
        ):
            raise ValueError("Unknown or invalid SELF CPU counter")
    total = user + system
    if not math.isfinite(total):
        raise ValueError("Invalid SELF CPU total")
    return {
        "schema": 1,
        "pid": pid,
        "ppid": ppid,
        "orig_argv": argv,
        "user_seconds": user,
        "system_seconds": system,
        "self_cpu_seconds": total,
        "scope": "SELF process, all threads, excludes descendants/non-Python processes",
        "acquisition": "stdlib os.times at early-registered atexit callback",
    }


def _write_self_cpu():
    times = os.times()
    record = cpu_record(
        os.getpid(), os.getppid(), list(sys.orig_argv), times.user, times.system
    )
    filename = os.path.join(_RECEIPT_DIR, f"python-{record['pid']}.json")
    with open(filename, "x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, indent=2) + "\n")


if _RECEIPT_DIR:
    atexit.register(_write_self_cpu)
