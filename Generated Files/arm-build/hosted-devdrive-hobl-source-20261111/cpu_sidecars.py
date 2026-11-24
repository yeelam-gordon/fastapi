"""Postterminal ABI2 validation and descriptive own-process intervals only."""

import json
import math
from pathlib import Path

from matched_audit import require


def validate(folder, enabled, identities, receipt, *, workers=4):
    require(type(workers) is int and workers in (3, 4), "expected three or four workers")
    roles = {"controller", *(f"gw{i}" for i in range(workers))}
    require(
        receipt.returncode == 0
        and not receipt.timed_out
        and receipt.ownership_established
        and receipt.cleanup_complete
        and receipt.survivors is False
        and not receipt.errors,
        "terminal family failure overrides sidecar presence",
    )
    pids = {row["worker"]: row["pid"] for row in identities}
    require(
        len(identities) == len(roles)
        and pids.keys() == roles
        and len(set(pids.values())) == len(roles)
        and all(type(pid) is int and pid > 0 for pid in pids.values())
        and type(receipt.native_start_ns) is int
        and type(receipt.native_end_ns) is int
        and 0 <= receipt.native_start_ns <= receipt.native_end_ns,
        "exact unique native role identities and native clocks",
    )
    files = {path.name for path in Path(folder).glob("early-boundaries-*")}
    require(
        files
        == ({f"early-boundaries-{role}.json" for role in roles} if enabled else set()),
        "exact OFF/ON sidecar inventory",
    )
    result = {}
    for role in sorted(roles) if enabled else ():
        data = json.loads((Path(folder) / f"early-boundaries-{role}.json").read_text())
        require(
            set(data)
            == {
                "schema_version",
                "pid",
                "worker",
                "clock",
                "clock_scope",
                "cpu_scope",
                "sample_order",
                "events",
            }
            and type(data["schema_version"]) is int
            and data["schema_version"] == 2
            and type(data["pid"]) is int
            and data["pid"] == pids[role]
            and data["worker"] == role
            and data["clock"] == "time.monotonic_ns"
            and data["clock_scope"] == "same-host-only"
            and data["cpu_scope"] == "current-process-all-threads/no-children"
            and data["sample_order"] == "CPU-then-wall/non-atomic",
            "exact ABI2 identity/scope",
        )
        names = [
            "pytest_configure.entry",
            "pytest_configure.exit",
            "pytest_sessionstart.entry",
            "pytest_sessionstart.exit",
            "pytest_collection.entry",
        ]
        if role != "controller":
            names += ["pytest_collection_finish.entry", "pytest_collection_finish.exit"]
        names += [
            "pytest_collection.exit",
            "pytest_runtest_logreport.first_entry",
            "pytest_sessionfinish.entry",
            "pytest_sessionfinish.exit",
        ]
        events = data["events"]
        require(
            [event["name"] for event in events] == names,
            "complete natural hook sequence",
        )
        for event in events:
            require(
                set(event)
                == {"name", "monotonic_ns", "cpu_user_seconds", "cpu_system_seconds"}
                and type(event["monotonic_ns"]) is int
                and receipt.native_start_ns
                <= event["monotonic_ns"]
                <= receipt.native_end_ns
                and all(
                    type(event[key]) is float
                    and math.isfinite(event[key])
                    and event[key] >= 0
                    for key in ("cpu_user_seconds", "cpu_system_seconds")
                ),
                "finite nonnegative CPU and native wall bounds",
            )
        require(
            all(
                a["monotonic_ns"] < b["monotonic_ns"]
                and a["cpu_user_seconds"] <= b["cpu_user_seconds"]
                and a["cpu_system_seconds"] <= b["cpu_system_seconds"]
                for a, b in zip(events, events[1:], strict=False)
            ),
            "monotonic role counters",
        )
        reports = [
            json.loads(line)
            for line in (Path(folder) / f"phases-{role}.jsonl").read_text().splitlines()
        ]
        require(
            reports
            and all(
                row["pid"] == pids[role] and row["worker"] == role for row in reports
            )
            and events[-3]["monotonic_ns"]
            <= min(row["completion_monotonic_ns"] for row in reports)
            and max(row["completion_monotonic_ns"] for row in reports)
            <= events[-2]["monotonic_ns"],
            "first-report/sessionfinish role ordering",
        )
        result[role] = [
            {
                "from": a["name"],
                "to": b["name"],
                "wall_seconds": (b["monotonic_ns"] - a["monotonic_ns"]) / 1e9,
                "self_user_seconds": b["cpu_user_seconds"] - a["cpu_user_seconds"],
                "self_system_seconds": b["cpu_system_seconds"]
                - a["cpu_system_seconds"],
            }
            for a, b in zip(events, events[1:], strict=False)
        ]
    return result
