"""Strict public gate for privately selected, independently owned CPU records."""
import json

EXIT_REASONS = {
    71: "module_arguments", 72: "module_selection_schema", 73: "module_counts",
    74: "module_key_schema", 75: "module_key_range", 76: "module_multiowner",
    77: "module_stale_etlx", 78: "module_trace_loss", 79: "module_sample_identity",
    80: "module_stack_depth",
    81: "module_missing_stacks",
}

ALLOW = {"uv", "python", "python3", "python313", "ntdll", "kernel32", "kernelbase",
         "ucrtbase", "ntoskrnl", "ntkrnlmp", "hal", "win32k", "win32kbase",
         "win32kfull", "fltmgr", "ntfs", "refs", "fastfat", "volmgr", "volsnap",
         "mountmgr", "storport", "stornvme", "disk", "classpnp", "fileinfo", "wdfilter"}
STACK_ALLOW = ALLOW | {"cng", "ci", "ntosext", "mup", "rdbss", "bindflt", "cldflt",
                       "wcifs", "wof", "fvevol", "storvsp", "wdf01000"}


def validate(value, result):
    fixed = dict(schema=1, cpu_units="SAMPLE_COUNTS", missing_samples=0,
                 unexpected_samples=0, symbol_resolution="DISABLED",
                 scheduling="UNSUPPORTED", file_durations="UNSUPPORTED",
                 interpretation="MODULE_PROVENANCE_NOT_EXECUTION_MODE_CAUSE_OR_IO_LATENCY",
                 stack_interpretation="INCLUSIVE_DEDUPLICATED_PRESENCE_NOT_CPU_TIME_OR_LATENCY")
    if type(value) is not dict or set(value) != set(fixed) | {"cpu_samples", "lifetimes", "modules", "stack_modules"}:
        raise ValueError("module_schema")
    if any(type(value[k]) is not type(v) or value[k] != v for k, v in fixed.items()):
        raise ValueError("module_schema")
    counts = [r["cpu_samples"] for r in result["lifetimes"]]
    if not 1 <= len(counts) <= 128:
        raise ValueError("module_counts")
    if type(value["cpu_samples"]) is not int or value["cpu_samples"] != result["cpu_samples"]:
        raise ValueError("module_counts")
    if not isinstance(value["lifetimes"], list) or len(value["lifetimes"]) != len(counts):
        raise ValueError("module_counts")
    for i, row in enumerate(value["lifetimes"]):
        if (type(row) is not dict or
                set(row) != {"process_index", "cpu_samples", "with_stack", "without_stack",
                             "stack_frames", "unknown_frames"} or
                type(row["process_index"]) is not int or row["process_index"] != i or
                type(row["cpu_samples"]) is not int or row["cpu_samples"] != counts[i]):
            raise ValueError("module_counts")
        if (any(type(row[k]) is not int or row[k] < 0 for k in
                ("with_stack", "without_stack", "stack_frames", "unknown_frames")) or
                row["with_stack"] + row["without_stack"] != counts[i] or
                not row["with_stack"] <= row["stack_frames"] <= row["with_stack"] * 512 or
                row["unknown_frames"] > row["stack_frames"]):
            raise ValueError("module_counts")
    if sum(row["with_stack"] for row in value["lifetimes"]) == 0:
        raise ValueError("module_missing_stacks")
    totals, seen = [0] * len(counts), set()
    if not isinstance(value["modules"], list) or len(value["modules"]) > 128 * (len(ALLOW) + 3) * 3 * 4:
        raise ValueError("module_schema")
    for row in value["modules"]:
        if type(row) is not dict or set(row) != {"process_index", "provenance", "module", "sample_context", "samples"}:
            raise ValueError("module_schema")
        i, p, m, n = (row[k] for k in ("process_index", "provenance", "module", "samples"))
        context = row["sample_context"]
        if (type(i) is not int or not 0 <= i < len(counts) or type(n) is not int or
                not 0 < n <= result["cpu_samples"] or type(p) is not str or type(m) is not str or
                p not in {"kernel-table", "user-table", "unresolved"} or
                m not in ALLOW | {"other-kernel", "other-user", "unresolved"} or
                (p == "unresolved") != (m == "unresolved") or
                (m == "other-kernel" and p != "kernel-table") or
                (m == "other-user" and p != "user-table") or
                type(context) is not str or context not in {"PROCESS", "DPC", "ISR", "DPC_ISR"} or
                (i, p, m, context) in seen):
            raise ValueError("module_schema")
        seen.add((i, p, m, context))
        totals[i] += n
    if totals != counts or sum(totals) != value["cpu_samples"]:
        raise ValueError("module_counts")
    if type(value["stack_modules"]) is not list:
        raise ValueError("module_schema")
    # Inclusive totals deliberately do not reconcile to CPU samples.
    seen = set()
    if len(value["stack_modules"]) > 128 * (len(STACK_ALLOW) + 3) * 3 * 4:
        raise ValueError("module_schema")
    presence_totals = [0] * len(counts)
    unresolved_presence = [0] * len(counts)
    for row in value["stack_modules"]:
        if type(row) is not dict or set(row) != {"process_index", "provenance", "module", "sample_context", "samples"}:
            raise ValueError("module_schema")
        i, p, m, c, n = (row[k] for k in
                         ("process_index", "provenance", "module", "sample_context", "samples"))
        if (type(i) is not int or not 0 <= i < len(counts) or
                type(n) is not int or not 0 < n <= value["lifetimes"][i]["with_stack"] or
                type(p) is not str or p not in {"kernel-table", "user-table", "unresolved"} or
                type(m) is not str or m not in STACK_ALLOW | {"other-kernel", "other-user", "unresolved"} or
                (p == "unresolved") != (m == "unresolved") or
                (m == "other-kernel" and p != "kernel-table") or
                (m == "other-user" and p != "user-table") or
                (m in STACK_ALLOW - ALLOW and p != "kernel-table") or
                type(c) is not str or c not in {"PROCESS", "DPC", "ISR", "DPC_ISR"} or
                (i, p, m, c) in seen):
            raise ValueError("module_schema")
        seen.add((i, p, m, c))
        presence_totals[i] += n
        if p == "unresolved":
            unresolved_presence[i] += n
    for i, row in enumerate(value["lifetimes"]):
        if (not row["with_stack"] <= presence_totals[i] <= row["stack_frames"] or
                unresolved_presence[i] > row["with_stack"] or
                row["unknown_frames"] > unresolved_presence[i] * 512):
            raise ValueError("module_counts")
    if len(json.dumps(value, allow_nan=False)) > 262144:
        raise ValueError("module_schema")
