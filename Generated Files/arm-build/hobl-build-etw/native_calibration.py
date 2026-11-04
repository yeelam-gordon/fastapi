"""Private controlled wait proof; never qualifies build critical time."""

import ctypes
import threading
import time

import decode
import launch
import timing_model
import typed_events

HANDSHAKE = {
    "schema",
    "pid",
    "tid",
    "qpc_frequency",
    "thread_qpc_before",
    "creation_filetime",
    "filetime_after",
    "before_wait",
    "released",
    "after_wait",
    "work_end",
}
PUBLIC_KEYS = {
    "schema",
    "status",
    "reason",
    "frequency",
    "target_lifetimes",
    "waiting_ticks",
    "runnable_ticks",
    "scheduled_ticks",
    "unknown_ticks",
    "marker_window_ticks",
    "controlled_waiting_ticks",
}
REASONS = {
    "observed_wait_proof",
    "trace_loss",
    "incomplete_trace",
    "missing_target_lifetime",
    "missing_state_boundaries",
    "insufficient_wait",
    "marker_window_out_of_bounds",
}
FAILURE_REASONS = {
    "ambiguous_same_qpc_subject": "native_wait_subject_tie",
    "ambiguous_same_processor_qpc": "native_wait_cpu_tie",
    "ambiguous_self_switch": "native_wait_self_switch",
    "out_of_order_timing": "native_wait_event_order",
    "calibration_event_order": "native_wait_event_order",
    "calibration_source": "native_wait_source",
    "qpc_frequency_mismatch": "native_wait_frequency",
    "unsupported_clock": "native_wait_clock",
    "calibration_clock_conflict": "native_wait_clock",
    "calibration_owner_mismatch": "native_wait_owner",
    "calibration_thread_conflict": "native_wait_thread",
    "calibration_thread_birth": "native_wait_thread_birth",
    "native_creation_mismatch": "native_wait_birth_clock",
    "calibration_requires_schema2": "native_wait_schema",
}


def failure_reason(error):
    """Return only exact static tags; never publish exception text."""
    if (
        type(error) is ValueError
        and len(error.args) == 1
        and type(error.args[0]) is str
    ):
        return FAILURE_REASONS.get(error.args[0], "native_calibration")
    return "native_calibration"


def controlled_wait():
    """Run only newly owned threads; return private native markers."""
    api = ctypes.windll.kernel32
    ready, release, cancel = (threading.Event() for _ in range(3))
    values, failures = {}, []
    api.GetCurrentThread.restype = ctypes.c_void_p
    api.GetThreadTimes.argtypes = [ctypes.c_void_p] + [
        ctypes.POINTER(ctypes.c_ulonglong)
    ] * 4
    frequency = ctypes.c_longlong()
    if not api.QueryPerformanceFrequency(ctypes.byref(frequency)):
        raise ctypes.WinError()
    values.update(
        schema=1, qpc_frequency=frequency.value, thread_qpc_before=launch.qpc()
    )

    def target():
        try:
            times = [ctypes.c_ulonglong() for _ in range(4)]
            if not api.GetThreadTimes(
                api.GetCurrentThread(), *map(ctypes.byref, times)
            ):
                raise ctypes.WinError()
            values.update(
                pid=api.GetCurrentProcessId(),
                tid=api.GetCurrentThreadId(),
                creation_filetime=times[0].value,
                filetime_after=launch.filetime(),
                before_wait=launch.qpc(),
            )
            ready.set()
            if not release.wait(2) or cancel.is_set():
                raise ValueError("calibration_timeout")
            values["after_wait"] = launch.qpc()
            deadline = time.perf_counter() + 0.04
            while time.perf_counter() < deadline:
                sum(index * index for index in range(1000))
            values["work_end"] = launch.qpc()
            # Encourage a closing switch-out outside the qualification window;
            # only recorded scheduling boundaries can establish residency.
            time.sleep(0.02)
        except BaseException as error:
            failures.append(error)
        finally:
            ready.set()

    def waker():
        try:
            if not ready.wait(1) or cancel.wait(0.15):
                raise ValueError("calibration_timeout")
            values["released"] = launch.qpc()
        except BaseException as error:
            failures.append(error)
        finally:
            release.set()

    workers = [threading.Thread(target=target), threading.Thread(target=waker)]
    started = []
    try:
        for worker in workers:
            worker.start()
            started.append(worker)
        for worker in started:
            worker.join(3)
        if failures:
            raise ValueError("calibration_failed") from failures[0]
        if any(worker.is_alive() for worker in started):
            raise ValueError("calibration_failed")
    finally:
        cancel.set()
        release.set()
        ready.set()
        for worker in started:
            worker.join(3)
    if set(values) != HANDSHAKE:
        raise ValueError("calibration_handshake")
    return values


def validate_public(value):
    if (
        set(value) != PUBLIC_KEYS
        or value["schema"] != 1
        or value["status"] not in {"PASS", "UNQUALIFIED"}
        or value["reason"] not in REASONS
        or (value["status"] == "PASS") != (value["reason"] == "observed_wait_proof")
        or any(
            type(value[key]) is not int or not 0 <= value[key] < 2**63
            for key in PUBLIC_KEYS - {"status", "reason"}
        )
    ):
        raise ValueError("calibration_public_schema")


def qualify(path, anchor, handshake):
    """Strict schema2 + existing native process-birth proof + observed thread life."""
    if (
        not isinstance(handshake, dict)
        or set(handshake) != HANDSHAKE
        or any(
            type(value) is not int or not 0 <= value < 2**63
            for value in handshake.values()
        )
        or handshake["schema"] != 1
    ):
        raise ValueError("calibration_handshake")
    marks = [
        handshake[key]
        for key in (
            "thread_qpc_before",
            "before_wait",
            "released",
            "after_wait",
            "work_end",
        )
    ]
    if not all(left < right for left, right in zip(marks, marks[1:], strict=False)):
        raise ValueError("calibration_marker_order")
    records = list(typed_events.rows(path))
    if any(row["schema"] != 2 for row in records):
        raise ValueError("calibration_requires_schema2")
    headers = [row for row in records if row["kind"] == "header"]
    if len(headers) != 1:
        raise ValueError("calibration_header")
    header = headers[0]
    frequency = header["payload"]["perfFreq"]
    if frequency <= 0 or header["payload"]["reservedFlags"] & 3 != 1:
        raise ValueError("unsupported_clock")
    if anchor["qpc_frequency"] != frequency or handshake["qpc_frequency"] != frequency:
        raise ValueError("qpc_frequency_mismatch")
    result = {
        "schema": 1,
        "status": "UNQUALIFIED",
        "reason": "incomplete_trace",
        "frequency": frequency,
        "target_lifetimes": 0,
        "waiting_ticks": 0,
        "runnable_ticks": 0,
        "scheduled_ticks": 0,
        "unknown_ticks": 0,
        "marker_window_ticks": marks[2] - marks[1],
        "controlled_waiting_ticks": 0,
    }

    def finish(reason):
        result["reason"] = reason
        result["status"] = "PASS" if reason == "observed_wait_proof" else "UNQUALIFIED"
        validate_public(result)
        return result

    if header["payload"]["eventsLost"] or header["payload"]["buffersLost"]:
        return finish("trace_loss")
    clock, process_lives, _ = decode.scan(path, typed_events.events)
    try:
        owned = decode.family(process_lives, anchor, frequency)
    except ValueError as error:
        if error.args == ("incomplete_lifetime",):
            return finish("incomplete_trace")
        raise
    if not (
        clock["qpc_start"] <= anchor["qpc_before"] < marks[0]
        and marks[-1] < anchor["qpc_end"] <= clock["last_qpc"]
        and clock["EndTime"] > clock["StartTime"]
    ):
        return finish("incomplete_trace")
    if any(
        row["kind"] != "header"
        and not clock["qpc_start"] <= row["qpc"] <= header["payload"]["lastQpc"]
        for row in records
    ):
        raise ValueError("calibration_clock_conflict")
    # family() supplies the same PID+birth/native-creation proof used by analyze().
    owners = [
        life
        for life in owned
        if life["pid"] == handshake["pid"]
        and life["start"] <= marks[0] < marks[-1] < life["end"]
    ]
    if len(owners) != 1:
        raise ValueError("calibration_owner_mismatch")
    owner = owners[0]
    active, lives = {}, []
    previous = -1
    for row in records:
        if row["kind"] == "header":
            continue
        if row["qpc"] < previous:
            raise ValueError("calibration_event_order")
        previous = row["qpc"]
        if row["kind"] not in {"threadStart", "threadStop", "cswitch", "readyThread"}:
            continue
        opcode = {"threadStart": 1, "threadStop": 2, "cswitch": 36, "readyThread": 50}
        if (
            row["provider"].lower() != decode.KERNEL[1:-1]
            or row["opcode"] != opcode[row["kind"]]
        ):
            raise ValueError("calibration_source")
        if row["kind"] == "threadStart":
            if row["tid"] in active:
                raise ValueError("calibration_thread_conflict")
            active[row["tid"]] = row
        elif row["kind"] == "threadStop":
            start = active.pop(row["tid"], None)
            if start is not None:
                if start["pid"] != row["pid"] or start["qpc"] >= row["qpc"]:
                    raise ValueError("calibration_thread_conflict")
                if (
                    row["tid"] == handshake["tid"]
                    and row["pid"] == owner["pid"]
                    and owner["start"] <= start["qpc"] <= marks[1]
                    and marks[-1] < row["qpc"] <= owner["end"]
                ):
                    if any(
                        event["processBirthQpc"] not in (None, owner["start"])
                        for event in (start, row)
                    ):
                        raise ValueError("calibration_owner_mismatch")
                    lives.append(
                        {
                            "tid": row["tid"],
                            "owner": "target",
                            "start": start["qpc"],
                            "end": row["qpc"],
                        }
                    )
    if len(lives) != 1:
        return finish("missing_target_lifetime")
    life = lives[0]
    if not marks[0] <= life["start"] <= marks[1]:
        raise ValueError("calibration_thread_birth")
    delta = abs(
        (life["start"] - marks[1]) / frequency
        - (handshake["creation_filetime"] - handshake["filetime_after"]) / 10_000_000
    )
    if delta > 0.1:
        raise ValueError("native_creation_mismatch")
    result["target_lifetimes"] = 1
    partition = timing_model.model(
        path,
        lifetimes=lives,
        owner_keys={"target"},
        window=(marks[1], marks[-1]),
        frequency=frequency,
    )["threads"][0]
    for state, ticks in partition["ticks"].items():
        result[state.lower() + "_ticks"] = ticks
    result["controlled_waiting_ticks"] = sum(
        max(0, min(interval["end"], marks[2]) - max(interval["start"], marks[1]))
        for interval in partition["intervals"]
        if interval["state"] == "WAITING"
        and marks[1] <= interval["start"] < marks[2] <= interval["end"] <= marks[3]
    )
    if not frequency // 10 <= result["marker_window_ticks"] <= frequency:
        return finish("marker_window_out_of_bounds")
    if result["controlled_waiting_ticks"] * 50 < frequency:
        return finish("insufficient_wait")
    post_wake_residency = any(
        interval["state"] == "SCHEDULED"
        and max(interval["start"], marks[3]) < min(interval["end"], marks[4])
        for interval in partition["intervals"]
    )
    if not post_wake_residency or not all(
        result[key] > 0
        for key in ("waiting_ticks", "runnable_ticks", "scheduled_ticks")
    ):
        return finish("missing_state_boundaries")
    return finish("observed_wait_proof")
