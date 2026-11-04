"""Private explicit thread lifetimes within an independently proven process."""

import decode


def collect(records, owner, owner_key):
    active, lives = {}, []
    counts = {"unclosed": 0, "unresolved": 0, "censored": 0}
    previous = -1
    for row in records:
        kind, qpc = row["kind"], row["qpc"]
        if kind == "header":
            continue
        if qpc < previous:
            raise ValueError("calibration_event_order")
        previous = qpc
        opcodes = {
            "threadStart": 1,
            "threadStop": 2,
            "threadDCStart": 3,
            "threadDCStop": 4,
            "cswitch": 36,
            "readyThread": 50,
        }
        if kind in opcodes and (
            row["provider"].lower() != decode.KERNEL[1:-1]
            or row["opcode"] != opcodes[kind]
        ):
            raise ValueError("calibration_source")
        relevant = row["pid"] == owner["pid"]
        if kind.startswith("thread") and relevant:
            if row["tid"] < 0:
                raise ValueError("calibration_thread_conflict")
            if row["processBirthQpc"] not in (None, owner["start"]):
                raise ValueError("calibration_owner_mismatch")
        if kind in {"threadDCStart", "threadDCStop"} and relevant:
            counts["unresolved"] += 1
        if kind == "threadStart":
            if row["tid"] in active:
                raise ValueError("calibration_thread_conflict")
            active[row["tid"]] = row
        elif kind == "threadStop":
            start = active.pop(row["tid"], None)
            if start is None:
                counts["unresolved"] += int(relevant)
                continue
            if start["pid"] != row["pid"] or start["qpc"] >= qpc:
                raise ValueError("calibration_thread_conflict")
            if relevant:
                if not owner["start"] <= start["qpc"] < qpc <= owner["end"]:
                    counts["censored"] += 1
                    continue
                lives.append(
                    {
                        "tid": row["tid"],
                        "owner": owner_key,
                        "start": start["qpc"],
                        "end": qpc,
                    }
                )
    counts["unclosed"] = sum(row["pid"] == owner["pid"] for row in active.values())
    return lives, counts
