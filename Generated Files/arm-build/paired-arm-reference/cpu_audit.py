"""Portable adaptation of the validated LF reference's SELF receipt audit."""

import importlib.util
import json
import math
import os
import re
from pathlib import Path

from guards import require

HOOK = Path(__file__).resolve().parent / "cpu-hook"
STARTUP_CHECK = """
import importlib.util, json, sys
print(json.dumps({
    "existing_hooks": [name for name in ("sitecustomize", "usercustomize")
                       if name in sys.modules or importlib.util.find_spec(name) is not None],
    "trace": sys.gettrace() is not None, "profile": sys.getprofile() is not None,
}))
"""


def records(directory):
    require(
        not os.environ.get("HOBL_CPU_RECEIPT_DIR"),
        "The controller must not activate the SELF receipt hook",
    )
    spec = importlib.util.spec_from_file_location(
        "paired_cpu_schema", HOOK / "sitecustomize.py"
    )
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    rows, invalid = [], []
    for path in sorted(directory.glob("python-*.json")):
        try:
            row = json.loads(path.read_bytes())
            expected = hook.cpu_record(
                row["pid"],
                row["ppid"],
                row["orig_argv"],
                row["user_seconds"],
                row["system_seconds"],
            )
            require(
                row == expected and path.name == f"python-{row['pid']}.json",
                "Receipt schema/PID/SELF total mismatch",
            )
            rows.append(row)
        except (ValueError, KeyError, TypeError, RuntimeError) as error:
            invalid.append({"file": path.name, "error": str(error)})
    if len({row["pid"] for row in rows}) != len(rows):
        invalid.append({"error": "Duplicate Python PID"})
    return rows, invalid


def entry_matches(row, entry_pid):
    # macOS normally runs directly; Windows can insert a native venv redirector.
    return (
        isinstance(entry_pid, int)
        and not isinstance(entry_pid, bool)
        and (row["pid"] == entry_pid or row["ppid"] == entry_pid)
    )


def contains(argv, command):
    return any(argv[i : i + len(command)] == command for i in range(len(argv)))


def audit(directory, shards, entry_pid, stderr):
    rows, invalid = records(directory)
    pids, bad_shards = [], []
    for path in shards.glob(".coverage.*"):
        match = re.search(r"\.pid(\d+)\.", path.name)
        if match:
            pids.append(int(match[1]))
        else:
            bad_shards.append(path.name)
    main = [
        row
        for row in rows
        if contains(
            row["orig_argv"], ["-m", "coverage", "run", "-m", "pytest", "tests"]
        )
    ]
    cli = [
        row
        for row in rows
        if contains(
            row["orig_argv"],
            ["-m", "coverage", "run", "-m", "fastapi", "dev", "non_existent_file.py"],
        )
    ]
    by_pid = {row["pid"]: row for row in rows}
    missing = sorted(set(pids) - by_pid.keys())
    hook_errors = b"Error in sitecustomize" in stderr or b"atexit" in stderr
    complete = (
        not invalid
        and not bad_shards
        and not missing
        and not hook_errors
        and len(pids) == len(set(pids)) == 2
        and len(main) == len(cli) == 1
        and {main[0]["pid"], cli[0]["pid"]} == set(pids)
        and entry_matches(main[0], entry_pid)
    )
    return {
        "performance_eligible": False,
        "covered_worker_receipts_complete": complete,
        "expected_covered_Python_pids_from_shards": sorted(pids),
        "valid_observed_Python_processes": rows,
        "invalid_records": invalid,
        "invalid_shard_names": bad_shards,
        "missing_covered_pid_receipts": missing,
        "startup_or_atexit_error_seen": hook_errors,
        "entry_pid": entry_pid,
        "main_worker_receipt": main[0] if len(main) == 1 else None,
        "covered_CLI_receipt": cli[0] if len(cli) == 1 else None,
        **{
            f"observed_Python_self_{name}_seconds": math.fsum(row[key] for row in rows)
            if complete
            else None
            for name, key in (
                ("user", "user_seconds"),
                ("system", "system_seconds"),
                ("total", "self_cpu_seconds"),
            )
        },
        "scope": "Observed Python SELF CPU, all threads, excludes descendants/non-Python "
        "processes. Not whole OS tree or launcher CPU; incomplete totals unknown.",
        "registration_order": "Early sitecustomize atexit; coverage exits first under LIFO.",
    }


def smoke(directory, entry_pid, stderr):
    rows, invalid = records(directory)
    complete = (
        not invalid
        and not stderr
        and len(rows) == 1
        and entry_matches(rows[0], entry_pid)
        and rows[0]["orig_argv"][-2:] == ["-c", "pass"]
    )
    return {
        "performance_eligible": False,
        "complete": complete,
        "valid_observed_Python_processes": rows,
        "invalid_records": invalid,
        "entry_pid": entry_pid,
        "scope": "One no-test hook smoke; zero CPU is valid.",
    }
