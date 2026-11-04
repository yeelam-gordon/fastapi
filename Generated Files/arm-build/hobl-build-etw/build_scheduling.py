"""Auxiliary observed ROOT thread residency; never a process critical path."""

import decode
import native_calibration
import observed_threads
import timing_model
import typed_events

REASONS = {
    "observed_root_threads",
    "incomplete_trace",
    "trace_loss",
    "no_outside_child_window",
    "no_complete_root_threads",
}
COUNTS = {"complete", "unclosed", "unresolved", "censored"}
DIAGNOSTIC_KEYS = {
    "unsupported_self",
    "ambiguous_subject_qpc",
    "ambiguous_processor_qpc",
}
FAILURE_REASONS = {
    key: value.replace("native_wait_", "build_scheduling_")
    for key, value in native_calibration.FAILURE_REASONS.items()
}
FAILURE_REASONS.update(
    {
        "root_birth_window": "build_scheduling_owner",
        "duplicate_owned_pid": "build_scheduling_owner",
        "schema": "build_scheduling_schema",
        "build_scheduling_schema": "build_scheduling_schema",
        "build_scheduling_requires_native_proof": "build_scheduling_native_proof",
        "partition_conservation_failure": "build_scheduling_conservation",
        "build_scheduling_conservation": "build_scheduling_conservation",
        "overlapping_thread_lifetimes": "build_scheduling_thread",
        "build_scheduling_process_cpu": "build_scheduling_process_cpu",
    }
)
KEYS = {
    "schema",
    "status",
    "quality",
    "reason",
    "scope",
    "calibration",
    "frequency",
    "window_ticks",
    "window_offset_ticks",
    "known_scheduled_union_ticks",
    "coverage",
    "threads",
    "process_cpu",
}
THREAD_KEYS = {"index", "window_ticks", "diagnostics", *timing_model.STATES}
PROCESS_CPU_KEYS = {"status", "scope", "units", "kernel", "user"}


def validate_process_cpu(value):
    if (
        not isinstance(value, dict)
        or set(value) != PROCESS_CPU_KEYS
        or value["scope"] != "ROOT_PROCESS_LIFETIME"
        or value["units"] != "100ns"
    ):
        raise ValueError("build_scheduling_process_cpu")
    if value["status"] == "OBSERVED":
        if all(
            type(value[key]) is int and 0 <= value[key] < 2**63
            for key in ("kernel", "user")
        ):
            return
    elif value["status"] == "UNAVAILABLE":
        if value["kernel"] is None and value["user"] is None:
            return
    raise ValueError("build_scheduling_process_cpu")


def process_cpu(anchor):
    """Whole-process cumulative CPU counters, independent of the selected window."""
    keys = ("process_kernel_100ns", "process_user_100ns")
    present = [key in anchor for key in keys]
    if any(present) != all(present):
        raise ValueError("build_scheduling_process_cpu")
    value = {
        "status": "OBSERVED" if all(present) else "UNAVAILABLE",
        "scope": "ROOT_PROCESS_LIFETIME",
        "units": "100ns",
        "kernel": anchor[keys[0]] if all(present) else None,
        "user": anchor[keys[1]] if all(present) else None,
    }
    validate_process_cpu(value)
    return value


def quality(value):
    """Observation quality only; even bracketed rows do not prove full coverage."""
    if value["status"] == "UNQUALIFIED":
        return "UNQUALIFIED"
    if any(
        value["coverage"][key] for key in ("unclosed", "unresolved", "censored")
    ) or any(
        row["UNKNOWN"] or any(row["diagnostics"].values()) for row in value["threads"]
    ):
        return "PARTIAL"
    return "BRACKETED_OBSERVATIONS"


def failure_reason(error):
    """Map exact known literals only; arbitrary exception payloads stay private."""
    if (
        type(error) is ValueError
        and len(error.args) == 1
        and type(error.args[0]) is str
    ):
        return FAILURE_REASONS.get(error.args[0], "build_scheduling_invalid")
    return "build_scheduling_invalid"


def known_scheduled_union(partition):
    """Lower bound of any-thread observed scheduled residency, not exclusive CPU."""
    intervals = sorted(
        (interval["start"], interval["end"])
        for thread in partition["threads"]
        for interval in thread["intervals"]
        if interval["state"] == "SCHEDULED"
    )
    total, right = 0, 0
    for start, end in intervals:
        total += max(0, end - max(start, right))
        right = max(right, end)
    return total


def largest_window(root, children):
    """Earliest largest complement of the clipped DIRECT-child interval union."""
    cursor, windows = root["start"], []
    for left, right in sorted(
        (max(root["start"], child["start"]), min(root["end"], child["end"]))
        for child in children
    ):
        if left >= right:
            continue
        if cursor < left:
            windows.append((cursor, left))
        cursor = max(cursor, right)
    if cursor < root["end"]:
        windows.append((cursor, root["end"]))
    return max(windows, key=lambda pair: (pair[1] - pair[0], -pair[0]), default=None)


def validate_public(value):
    if (
        not isinstance(value, dict)
        or set(value) != KEYS
        or type(value["schema"]) is not int
        or value["schema"] != 1
        or value["status"] not in {"AUXILIARY", "UNQUALIFIED"}
        or value["reason"] not in REASONS
        or (value["status"] == "AUXILIARY")
        != (value["reason"] == "observed_root_threads")
        or value["scope"] != "ROOT_OUTSIDE_DIRECT_CHILD"
        or value["calibration"] != "SAME_SESSION_CONTROLLED_WAIT_PASS"
        or not isinstance(value["coverage"], dict)
        or set(value["coverage"]) != COUNTS
        or not isinstance(value["threads"], list)
    ):
        raise ValueError("build_scheduling_schema")
    validate_process_cpu(value["process_cpu"])
    numbers = [
        value[key]
        for key in (
            "frequency",
            "window_ticks",
            "window_offset_ticks",
            "known_scheduled_union_ticks",
        )
    ]
    numbers += list(value["coverage"].values())
    for index, row in enumerate(value["threads"]):
        if (
            not isinstance(row, dict)
            or set(row) != THREAD_KEYS
            or row["index"] != index
            or not isinstance(row["diagnostics"], dict)
            or set(row["diagnostics"]) != DIAGNOSTIC_KEYS
        ):
            raise ValueError("build_scheduling_schema")
        numbers += [row[key] for key in THREAD_KEYS - {"diagnostics"}]
        numbers += list(row["diagnostics"].values())
    if any(type(number) is not int or not 0 <= number < 2**63 for number in numbers):
        raise ValueError("build_scheduling_schema")
    for row in value["threads"]:
        if sum(row[state] for state in timing_model.STATES) != row["window_ticks"]:
            raise ValueError("build_scheduling_conservation")
        if not 0 < row["window_ticks"] <= value["window_ticks"]:
            raise ValueError("build_scheduling_schema")
    scheduled = [row["SCHEDULED"] for row in value["threads"]]
    if not (
        max(scheduled, default=0)
        <= value["known_scheduled_union_ticks"]
        <= min(value["window_ticks"], sum(scheduled))
    ):
        raise ValueError("build_scheduling_conservation")
    if value["status"] == "AUXILIARY" and (
        not value["threads"] or value["frequency"] <= 0 or value["window_ticks"] <= 0
    ):
        raise ValueError("build_scheduling_schema")
    if value["quality"] != quality(value):
        raise ValueError("build_scheduling_schema")


def qualify(path, anchor, calibration):
    """Re-prove this trace's ownership/clock; controlled calibration is not ownership."""
    native_calibration.validate_public(calibration)
    if calibration["status"] != "PASS":
        raise ValueError("build_scheduling_requires_native_proof")
    cpu = process_cpu(anchor)
    records = list(typed_events.rows(path))
    if any(row["schema"] != 2 for row in records):
        raise ValueError("build_scheduling_schema")
    headers = [row for row in records if row["kind"] == "header"]
    if len(headers) != 1:
        raise ValueError("build_scheduling_schema")
    payload = headers[0]["payload"]
    frequency = payload["perfFreq"]
    if frequency <= 0 or payload["reservedFlags"] & 3 != 1:
        raise ValueError("unsupported_clock")
    if frequency != anchor["qpc_frequency"] or frequency != calibration["frequency"]:
        raise ValueError("qpc_frequency_mismatch")
    public = {
        "schema": 1,
        "status": "UNQUALIFIED",
        "quality": "UNQUALIFIED",
        "reason": "incomplete_trace",
        "scope": "ROOT_OUTSIDE_DIRECT_CHILD",
        "calibration": "SAME_SESSION_CONTROLLED_WAIT_PASS",
        "frequency": frequency,
        "window_ticks": 0,
        "window_offset_ticks": 0,
        "known_scheduled_union_ticks": 0,
        "coverage": dict.fromkeys(COUNTS, 0),
        "threads": [],
        "process_cpu": cpu,
    }
    private = {"schema": 1, "partition": None}

    def finish(reason):
        public["reason"] = reason
        public["status"] = (
            "AUXILIARY" if reason == "observed_root_threads" else "UNQUALIFIED"
        )
        public["quality"] = quality(public)
        validate_public(public)
        return public, private

    if payload["eventsLost"] or payload["buffersLost"]:
        return finish("trace_loss")
    if any(
        row["kind"] != "header"
        and not headers[0]["qpc"] <= row["qpc"] <= payload["lastQpc"]
        for row in records
    ):
        raise ValueError("calibration_clock_conflict")
    # Validate process sources before reusing the existing PID/native-birth graph proof.
    active = {}
    for row in records:
        if row["kind"] not in {"processStart", "processStop"}:
            continue
        if row["provider"].lower() != decode.KERNEL[1:-1] or row["opcode"] != (
            1 if row["kind"] == "processStart" else 2
        ):
            raise ValueError("calibration_source")
        if row["kind"] == "processStart":
            if (
                row["pid"] < 0
                or row["payload"]["parentPid"] == row["pid"]
                or row["processBirthQpc"] not in (None, row["qpc"])
            ):
                raise ValueError("calibration_owner_mismatch")
            if row["pid"] in active:
                raise ValueError("duplicate_owned_pid")
            active[row["pid"]] = row
        else:
            start = active.pop(row["pid"], None)
            if start is not None and (
                start["qpc"] >= row["qpc"]
                or start["payload"] != row["payload"]
                or any(
                    event["processBirthQpc"] not in (None, start["qpc"])
                    for event in (start, row)
                )
            ):
                raise ValueError("calibration_owner_mismatch")
    clock, process_lives, _ = decode.scan(path, typed_events.events)
    try:
        owned = decode.family(process_lives, anchor, frequency)
    except ValueError as error:
        if error.args == ("incomplete_lifetime",):
            return finish("incomplete_trace")
        raise
    root = owned[0]
    if not (
        clock["qpc_start"]
        <= anchor["qpc_before"]
        <= root["start"]
        < root["end"]
        <= anchor["qpc_end"]
        <= payload["lastQpc"]
        and clock["EndTime"] > clock["StartTime"]
        and 0 < anchor["qpc_end"] - anchor["qpc_before"] <= 10 * frequency
    ):
        return finish("incomplete_trace")
    lives, counts = observed_threads.collect(records, root, "process-index-0")
    public["coverage"].update(counts, complete=len(lives))
    window = largest_window(
        root, [life for life in owned[1:] if life["parent"] == root["pid"]]
    )
    if window is None:
        return finish("no_outside_child_window")
    public.update(
        window_ticks=window[1] - window[0],
        window_offset_ticks=window[0] - root["start"],
    )
    lives = [
        life for life in lives if life["start"] < window[1] and window[0] < life["end"]
    ]
    if not lives:
        return finish("no_complete_root_threads")
    private["partition"] = timing_model.model(
        path,
        lifetimes=lives,
        owner_keys={"process-index-0"},
        window=window,
        frequency=frequency,
    )
    public["threads"] = [
        dict(
            index=index,
            window_ticks=thread["window"][1] - thread["window"][0],
            diagnostics=dict(thread["diagnostics"]),
            **thread["ticks"],
        )
        for index, thread in enumerate(private["partition"]["threads"])
    ]
    public["known_scheduled_union_ticks"] = known_scheduled_union(private["partition"])
    return finish("observed_root_threads")
