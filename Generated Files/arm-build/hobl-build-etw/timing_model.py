"""PRIVATE offline scheduling prototype; synthetic-only, not native-qualified.

Inputs are validated private DTOs plus independently observed, half-open thread
lifetimes. Only intervals bracketed by compatible observations are classified.
Scheduled residency includes interrupt/VM uncertainty, not exclusive CPU time.
"""

from fractions import Fraction
from itertools import groupby

import typed_events

STATES = ("UNKNOWN", "WAITING", "RUNNABLE", "SCHEDULED")


def _integer(value, name, minimum=0, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid_" + name)
    return value


def seconds(ticks, frequency):
    """Explicit exact conversion; no CPU-count normalization."""
    return Fraction(_integer(ticks, "ticks"), _integer(frequency, "frequency", 1))


def _rows(path):
    try:
        yield from typed_events.rows(path)
    except (TypeError, KeyError) as error:
        raise ValueError("invalid_timing_schema") from error


def model(path, *, lifetimes, owner_keys, window, frequency):
    """Return private per-lifetime partitions, never a cross-thread critical path.

    lifetimes: dictionaries {tid, owner, start, end}, independently observed;
    owner is a nonempty opaque string. TID reuse requires disjoint lifetimes.
    window and lifetimes are half-open integer QPC ranges. Missing closing
    observations remain UNKNOWN; no backwards extension from a switch-out.
    Any legacy scheduling record makes scheduling unavailable for this input.
    Ambiguity guards concern selected observed lifetimes and their originating
    processor associations, not unrelated machine-wide scheduling activity.
    Unsupported observations become UNKNOWN boundaries with fixed lifetime-wide
    diagnostic counts; malformed inputs and decreasing scheduling QPC still fail.
    """
    _integer(frequency, "frequency", 1)
    if not isinstance(window, (tuple, list)) or len(window) != 2:
        raise ValueError("invalid_window")
    begin, end = (_integer(value, "window") for value in window)
    if begin >= end:
        raise ValueError("empty_window")
    if (
        not isinstance(owner_keys, (tuple, list, set, frozenset))
        or not owner_keys
        or any(not isinstance(key, str) or not key for key in owner_keys)
    ):
        raise ValueError("invalid_owner_keys")
    if not isinstance(lifetimes, (tuple, list)) or not lifetimes:
        raise ValueError("invalid_lifetimes")
    lives, by_tid = [], {}
    for supplied in lifetimes:
        if not isinstance(supplied, dict) or set(supplied) != {
            "tid",
            "owner",
            "start",
            "end",
        }:
            raise ValueError("invalid_lifetime_schema")
        life = dict(supplied)
        _integer(life["tid"], "lifetime_tid", 0, 2**31 - 1)
        _integer(life["start"], "lifetime_start")
        _integer(life["end"], "lifetime_end")
        if not isinstance(life["owner"], str) or not life["owner"]:
            raise ValueError("invalid_lifetime_owner")
        if life["start"] >= life["end"]:
            raise ValueError("empty_lifetime")
        by_tid.setdefault(life["tid"], []).append(life)
        lives.append(life)
    for group in by_tid.values():
        group.sort(key=lambda life: life["start"])
        if any(
            left["end"] > right["start"]
            for left, right in zip(group, group[1:], strict=False)
        ):
            raise ValueError("overlapping_thread_lifetimes")

    if not any(
        life["owner"] in owner_keys and life["start"] < end and begin < life["end"]
        for life in lives
    ):
        raise ValueError("selected_lifetime_unavailable")
    by_tid = {
        tid: [
            life
            for life in group
            if life["owner"] in owner_keys
            and life["start"] < end
            and begin < life["end"]
        ]
        for tid, group in by_tid.items()
    }
    observations = {id(life): [] for life in lives}
    diagnostics = {
        id(life): dict.fromkeys(
            ("unsupported_self", "ambiguous_subject_qpc", "ambiguous_processor_qpc"), 0
        )
        for life in lives
    }
    running = {}
    previous, legacy = None, False
    timing = (row for row in _rows(path) if row["kind"] in {"cswitch", "readyThread"})
    for qpc, group in groupby(timing, key=lambda row: row["qpc"]):
        if previous is not None and qpc < previous:
            raise ValueError("out_of_order_timing")
        previous = qpc
        group = list(group)
        switched = {}
        for row in group:
            if row["schema"] == 2 and row["kind"] == "cswitch":
                processor = row["payload"]["processorNumber"]
                switched[processor] = switched.get(processor, 0) + 1
        affected, updates, clear = {}, {}, set()
        for row in group:
            payload = row["payload"]
            if row["schema"] != 2:
                legacy = True
                continue
            if row["kind"] == "cswitch":
                targets = [(payload["oldTid"], "out"), (payload["newTid"], "in")]
                if payload["oldTid"] == payload["newTid"]:
                    targets = [(payload["newTid"], "self")]
                processor = payload["processorNumber"]
                association = running.get(processor)
                if association is not None:
                    previous_tid, observed_qpc = association
                    if previous_tid not in {
                        payload["oldTid"],
                        payload["newTid"],
                    } and any(
                        life["start"] <= observed_qpc <= qpc < life["end"]
                        for life in by_tid.get(previous_tid, ())
                    ):
                        targets.append((previous_tid, "gap"))
                updates[processor] = (payload["newTid"], qpc)
            else:
                targets = [(payload["awakenedTid"], "ready")]
            for tid, action in targets:
                for life in by_tid.get(tid, ()):
                    if life["start"] <= qpc < life["end"]:
                        if action == "self" and (
                            tid == 0
                            or association is None
                            or association[0] != tid
                            or not life["start"] <= association[1] < qpc
                        ):
                            action = "unsupported_self"
                        affected.setdefault(id(life), (life, []))[1].append(
                            (action, payload)
                        )
        for identity, (life, items) in affected.items():
            subject = observations[identity]
            subject_tie = len(items) > 1
            processor_tie = any(
                switched.get(payload.get("processorNumber"), 0) > 1
                for action, payload in items
                if action != "ready"
            )
            diagnostics[identity]["ambiguous_subject_qpc"] += int(subject_tie)
            diagnostics[identity]["ambiguous_processor_qpc"] += int(processor_tie)
            if subject_tie or processor_tie:
                action = "ambiguous_subject_qpc" if subject_tie else "ambiguous_processor_qpc"
                payload = {}
            else:
                action, payload = items[0]
                if action == "self" and (
                    not subject
                    or subject[-1][1] not in {"in", "self"}
                    or subject[-1][2]["processorNumber"] != payload["processorNumber"]
                ):
                    action = "unsupported_self"
                diagnostics[identity]["unsupported_self"] += int(action == "unsupported_self")
            if subject_tie or processor_tie or action == "unsupported_self":
                clear.update(
                    cpu for cpu, (tid, origin) in running.items()
                    if tid == life["tid"] and life["start"] <= origin <= qpc < life["end"]
                )
                clear.update(
                    payload["processorNumber"] for action, payload in items if action != "ready"
                )
            subject.append((qpc, action, payload))
        for processor, association in updates.items():
            if switched[processor] == 1 and processor not in clear:
                running[processor] = association
            else:
                running.pop(processor, None)
        for processor in clear:
            running.pop(processor, None)

    results = []
    for life in lives:
        if life["owner"] not in owner_keys:
            continue
        left, right = max(begin, life["start"]), min(end, life["end"])
        if left >= right:
            continue
        intervals = []

        def append(
            start, stop, state, reason, *, left=left, right=right, intervals=intervals
        ):
            start, stop = max(left, start), min(right, stop)
            if start < stop:
                intervals.append(
                    {"start": start, "end": stop, "state": state, "reason": reason}
                )

        cursor, state, processor = life["start"], "UNKNOWN", None
        atomic_self_switches = 0
        unknown_reason = "missing_closing_boundary"
        for qpc, action, payload in () if legacy else observations[id(life)]:
            if action == "self":
                atomic_self_switches += int(left <= qpc < right)
            unsupported = action in diagnostics[id(life)]
            compatible = (
                (
                    state == "SCHEDULED"
                    and action in {"out", "self"}
                    and processor == payload["processorNumber"]
                )
                or (state == "WAITING" and action == "ready" and payload["flags"] == 0)
                or (state == "RUNNABLE" and action == "in")
                or (state == "RUNNABLE" and action == "ready" and payload["flags"] == 0)
            )
            append(
                cursor,
                qpc,
                state if compatible else "UNKNOWN",
                "atomic_self_switch_accounting"
                if action == "self"
                else action
                if unsupported
                else "bracketed_observations"
                if compatible
                else unknown_reason
                if state == "UNKNOWN"
                else "missing_or_conflicting_boundary",
            )
            if action in {"in", "self"}:
                state, processor = "SCHEDULED", payload["processorNumber"]
            elif action == "out":
                state = {1: "RUNNABLE", 5: "WAITING"}.get(
                    payload["oldThreadState"], "UNKNOWN"
                )
                processor = None
            elif action == "gap" or unsupported:
                state, processor = "UNKNOWN", None
            elif payload["flags"] != 0 or state == "SCHEDULED":
                state, processor = "UNKNOWN", None
            else:
                state, processor = "RUNNABLE", None
            unknown_reason = action if unsupported else "missing_or_conflicting_boundary"
            cursor = qpc
        append(
            cursor,
            life["end"],
            "UNKNOWN",
            "legacy_schema_unavailable"
            if legacy
            else unknown_reason
            if state == "UNKNOWN"
            else "missing_closing_boundary",
        )
        totals = {
            state: sum(
                item["end"] - item["start"]
                for item in intervals
                if item["state"] == state
            )
            for state in STATES
        }
        if (
            sum(totals.values()) != right - left
            or not intervals
            or intervals[0]["start"] != left
            or intervals[-1]["end"] != right
            or any(
                a["end"] != b["start"]
                for a, b in zip(intervals, intervals[1:], strict=False)
            )
        ):
            raise ValueError("partition_conservation_failure")
        results.append(
            {
                "lifetime": dict(life),
                "window": (left, right),
                "intervals": intervals,
                "ticks": totals,
                "quality": "UNKNOWN_PRESENT" if totals["UNKNOWN"] else "BRACKETED_ONLY",
                "atomic_self_switches": atomic_self_switches,
                "diagnostics": diagnostics[id(life)],
            }
        )
    return {
        "status": "UNAVAILABLE_LEGACY" if legacy else "SYNTHETIC_ONLY_UNQUALIFIED",
        "frequency": frequency,
        "threads": results,
        "interpretation": "scheduled residency, not exclusive CPU or critical path",
    }
