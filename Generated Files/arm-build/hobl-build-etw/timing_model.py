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
    Equal-QPC records require disjoint observed subjects and switch processors.
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
    observations = {id(life): [] for life in lives}
    running = {}
    previous, legacy = None, False
    timing = (row for row in _rows(path) if row["kind"] in {"cswitch", "readyThread"})
    for qpc, group in groupby(timing, key=lambda row: row["qpc"]):
        if previous is not None and qpc < previous:
            raise ValueError("out_of_order_timing")
        previous = qpc
        switched = set()
        for row in group:
            payload = row["payload"]
            if row["schema"] != 2:
                legacy = True
                continue
            if row["kind"] == "cswitch":
                if payload["oldTid"] == payload["newTid"]:
                    raise ValueError("ambiguous_self_switch")
                targets = [(payload["oldTid"], "out"), (payload["newTid"], "in")]
                processor = payload["processorNumber"]
                if processor in switched:
                    raise ValueError("ambiguous_same_processor_qpc")
                switched.add(processor)
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
                running[processor] = (payload["newTid"], qpc)
            else:
                targets = [(payload["awakenedTid"], "ready")]
            for tid, action in targets:
                for life in by_tid.get(tid, ()):
                    if life["start"] <= qpc < life["end"]:
                        subject = observations[id(life)]
                        if subject and subject[-1][0] == qpc:
                            raise ValueError("ambiguous_same_qpc_subject")
                        subject.append((qpc, action, payload))

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
        for qpc, action, payload in () if legacy else observations[id(life)]:
            compatible = (
                (
                    state == "SCHEDULED"
                    and action == "out"
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
                "bracketed_observations"
                if compatible
                else "missing_or_conflicting_boundary",
            )
            if action == "in":
                state, processor = "SCHEDULED", payload["processorNumber"]
            elif action == "out":
                state = {1: "RUNNABLE", 5: "WAITING"}.get(
                    payload["oldThreadState"], "UNKNOWN"
                )
                processor = None
            elif action == "gap":
                state, processor = "UNKNOWN", None
            elif payload["flags"] != 0 or state == "SCHEDULED":
                state, processor = "UNKNOWN", None
            else:
                state, processor = "RUNNABLE", None
            cursor = qpc
        append(
            cursor,
            life["end"],
            "UNKNOWN",
            "legacy_schema_unavailable" if legacy else "missing_closing_boundary",
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
            }
        )
    return {
        "status": "UNAVAILABLE_LEGACY" if legacy else "SYNTHETIC_ONLY_UNQUALIFIED",
        "frequency": frequency,
        "threads": results,
        "interpretation": "scheduled residency, not exclusive CPU or critical path",
    }
