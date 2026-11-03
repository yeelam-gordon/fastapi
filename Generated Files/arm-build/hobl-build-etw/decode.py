"""Streaming consumer of tracerpt -rts XML. Raw inputs never leave private storage."""
import collections
import json
import math
import xml.etree.ElementTree as ET

NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"
TRACE = "{http://schemas.microsoft.com/win/2004/08/events/trace}"
MODULES = {"uv.exe", "python.exe", "python3.dll", "python313.dll", "ntdll.dll",
           "kernelbase.dll", "kernel32.dll", "ucrtbase.dll"}
KERNEL = "{9e814aad-3204-11d2-9a82-006008a86939}"


def number(value):
    text = str(value).strip()
    return int(text, 16 if text.lower().startswith("0x") else 10)


def events(path):
    context = ET.iterparse(path, events=("start", "end"))
    _, root = next(context)
    for action, element in context:
        if action != "end" or element.tag != NS + "Event":
            continue
        system = element.find(NS + "System")
        data = {x.get("Name"): x.text or "" for x in element.findall(NS + "EventData/" + NS + "Data")}
        name = element.findtext(".//" + TRACE + "EventName", "")
        execution = system.find(NS + "Execution")
        yield {
            "name": name, "data": data,
            "qpc": number(system.find(NS + "TimeCreated").get("RawTime")),
            "version": number(system.findtext(NS + "Version", "0")),
            "opcode": number(system.findtext(NS + "Opcode", "0")),
            "id": number(system.findtext(NS + "EventID", "0")),
            "provider": system.find(NS + "Provider").get("Guid", "").lower(),
            "tid": number(execution.get("ThreadID", "0")),
        }
        element.clear()
        root.clear()


def scan(path):
    """Private metadata pass; no process identifiers or strings are published."""
    header, lives, active = None, [], {}
    counts = collections.Counter()
    last = 0
    for e in events(path):
        counts[e["name"] or "unnamed"] += 1
        last = max(last, e["qpc"])
        d = e["data"]
        if "PerfFreq" in d:
            header = {k: number(d[k]) for k in
                      ("PerfFreq", "ReservedFlags", "EventsLost", "BuffersLost", "StartTime", "EndTime")}
            header["qpc_start"] = e["qpc"]
        if e["provider"] != KERNEL or e["name"] != "Process" or e["version"] != 4:
            continue
        pid = number(d["ProcessId"])
        if e["opcode"] == 1:
            life = {"pid": pid, "parent": number(d["ParentId"]), "start": e["qpc"],
                    "end": None}
            lives.append(life)
            active[pid] = life
        elif e["opcode"] == 2 and pid in active:
            active.pop(pid)["end"] = e["qpc"]
    if not header or header["ReservedFlags"] & 3 != 1 or header["PerfFreq"] <= 0:
        raise ValueError("unsupported_clock")
    if header["EventsLost"] or header["BuffersLost"]:
        raise ValueError("trace_loss")
    header["last_qpc"] = last
    return header, lives, counts


def family(lives, anchor, freq):
    roots = [x for x in lives if x["pid"] == anchor["pid"]
             and anchor["qpc_before"] <= x["start"] <= anchor["qpc_after"]]
    if len(roots) != 1:
        raise ValueError("root_birth_window")
    root = roots[0]
    # Native creation FILETIME must agree independently with the QPC anchor.
    delta = abs((root["start"] - anchor["qpc_after"]) / freq -
                (anchor["creation_filetime"] - anchor["filetime_after"]) / 10_000_000)
    if delta > .1:
        raise ValueError("native_creation_mismatch")
    owned = [root]
    while True:
        added = [x for x in lives if x not in owned and any(
            x["parent"] == p["pid"] and p["start"] <= x["start"]
            and p["end"] is not None and x["start"] <= p["end"] for p in owned)]
        if not added:
            break
        owned.extend(added)
    if any(x["end"] is None for x in owned):
        raise ValueError("incomplete_lifetime")
    if len({x["pid"] for x in owned}) != len(owned):
        raise ValueError("duplicate_owned_pid")
    return owned


def analyze(path, anchor, calibration=False, child_anchor=None):
    h, lives, _ = scan(path)
    if anchor["qpc_frequency"] != h["PerfFreq"]:
        raise ValueError("qpc_frequency_mismatch")
    owned = family(lives, anchor, h["PerfFreq"])
    if calibration:
        if not child_anchor or child_anchor["qpc_frequency"] != h["PerfFreq"]:
            raise ValueError("missing_known_child")
        child_lives = family(lives, child_anchor, h["PerfFreq"])
        child = child_lives[0]
        if child not in owned or child is owned[0]:
            raise ValueError("known_child_not_owned")
    threads, images = {}, collections.defaultdict(list)
    samples, files, unresolved = collections.Counter(), 0, 0
    process_samples, process_files = collections.Counter(), collections.Counter()
    root_samples = 0
    fingerprints = set()
    file_names, known_file_operations = {}, 0
    start, stop = anchor["qpc_before"], anchor["qpc_end"]
    if stop <= start or (stop - start) / h["PerfFreq"] > 10:
        raise ValueError("recording_window")

    def owner(pid, q):
        return next((x for x in owned if x["pid"] == pid and x["start"] <= q <= x["end"]), None)

    for e in events(path):
        d, q, name = e["data"], e["qpc"], e["name"]
        if e["provider"] == KERNEL and name == "FileIo" and e["version"] == 2 and "FileObject" in d:
            obj = number(d["FileObject"])
            if e["opcode"] in (0, 32, 36) and "FileName" in d:
                file_names[obj] = d["FileName"].replace("/", "\\").lower().endswith("\\calibration-data.bin")
            elif e["opcode"] == 35:
                file_names.pop(obj, None)
        if e["provider"] == KERNEL and name == "Thread" and e["version"] == 3:
            tid, pid = number(d["TThreadId"]), number(d["ProcessId"])
            if e["opcode"] in (1, 3):
                threads[tid] = (pid, q)
            elif e["opcode"] == 2:
                threads.pop(tid, None)
        if e["provider"] == KERNEL and name == "Image" and e["version"] == 2:
            pid = number(d["ProcessId"])
            if owner(pid, q):
                base = number(d["ImageBase"])
                if e["opcode"] in (10, 3):
                    module = d["FileName"].replace("\\", "/").rsplit("/", 1)[-1].lower()
                    images[pid].append((base, number(d["ImageSize"]), module, q, None))
                    if module in MODULES and all(k in d for k in ("ImageChecksum", "TimeDateStamp")):
                        fingerprints.add((owned.index(owner(pid, q)), module, number(d["ImageChecksum"]),
                                          number(d["TimeDateStamp"]), number(d["ImageSize"])))
                elif e["opcode"] == 2:
                    images[pid] = [(b, s, m, t, q if b == base and end is None else end)
                                   for b, s, m, t, end in images[pid]]
        if not start <= q <= stop:
            continue
        tid = number(d.get("ThreadId", d.get("IssuingThreadId", d.get("TTID", e["tid"]))))
        subject = threads.get(tid)
        process_owner = owner(subject[0], q) if subject else None
        if process_owner is None:
            continue
        process_index = owned.index(process_owner)
        if e["provider"] == KERNEL and name == "PerfInfo" and e["opcode"] == 46 and e["version"] == 2:
            ip = number(d["InstructionPointer"])
            module = next((m for b, s, m, begin, end in reversed(images[subject[0]])
                           if b <= ip < b + s and begin <= q and (end is None or q <= end)), None)
            bucket = module if module in MODULES else "unresolved"
            samples[bucket] += 1
            process_samples[process_index] += 1
            root_samples += process_index == 0
            unresolved += bucket == "unresolved"
        # Count only actual issuing-thread operations, never name/rundown records.
        if ((e["provider"] == KERNEL and name == "DiskIo" and e["version"] == 3 and e["opcode"] in (10, 11)
             and all(k in d for k in ("IssuingThreadId", "Irp", "FileObject", "TransferSize")))
                or (e["provider"] == KERNEL and name == "FileIo" and e["version"] in (2, 3) and e["opcode"] in (64, 67, 68)
                    and ("Irp" in d or "IrpPtr" in d) and "FileObject" in d and ("TTID" in d or "IssuingThreadId" in d))
                or (e["provider"] == "{edd08927-9cc4-4e65-b970-c2560fb5c289}"
                    and e["version"] == 1 and e["id"] == 12)):
            files += 1
            process_files[process_index] += 1
            filename = d.get("OpenPath", d.get("FileName", "")).replace("/", "\\").lower()
            if filename.endswith("\\calibration-data.bin") or file_names.get(number(d.get("FileObject", "0")), False):
                known_file_operations += 1
    total = sum(samples.values())
    if (total < 1 or files < 1 or len(owned) < 2
            or (calibration and known_file_operations < 1)):
        raise ValueError("insufficient_owned_evidence")
    if calibration:
        child_indices = {owned.index(life) for life in child_lives}
        parent_indices = set(range(len(owned))) - child_indices
        if any(sum(counter[index] for index in indices) < 1
               for counter in (process_samples, process_files)
               for indices in (child_indices, parent_indices)):
            raise ValueError("insufficient_owned_evidence")
    result = {
        "schema": 1, "status": "PARTIAL", "family_lifetimes": len(owned),
        "cpu_samples": total, "file_operation_records": files,
        "root_cpu_samples": root_samples, "descendant_cpu_samples": total - root_samples,
        "lifetimes": [{"role": "ROOT" if x is owned[0] else "UNKNOWN_DESCENDANT",
                       "parent_index": None if x is owned[0] else next(
                           i for i, parent in enumerate(owned[:index])
                           if parent["pid"] == x["parent"] and parent["start"] <= x["start"] <= parent["end"]),
                       "start_seconds": (x["start"] - start) / h["PerfFreq"],
                       "end_seconds": (x["end"] - start) / h["PerfFreq"],
                       "cpu_samples": process_samples[index],
                       "file_operation_records": process_files[index]} for index, x in enumerate(owned)],
        "images": [{"process_index": i, "module": m, "checksum": c, "timestamp": t, "size_bytes": s}
                   for i, m, c, t, s in sorted(fingerprints)],
        "unresolved_samples": unresolved,
        "modules": [{"module": m, "samples": n, "fraction": n / total}
                    for m, n in sorted(samples.items())],
        "interval_seconds": (stop - start) / h["PerfFreq"],
        "trace_header_seconds": (h["EndTime"] - h["StartTime"]) / 10_000_000,
        "trace_event_seconds": (h["last_qpc"] - h["qpc_start"]) / h["PerfFreq"],
        "cpu_units": "SAMPLE_COUNTS", "scheduling": "UNSUPPORTED",
        "file_durations": "UNSUPPORTED", "hook_roles": "UNKNOWN",
        "events_lost": 0, "buffers_lost": 0,
    }
    validate(result)
    return result


def validate(value):
    keys = {"schema", "status", "family_lifetimes", "cpu_samples", "file_operation_records",
            "unresolved_samples", "modules", "interval_seconds", "trace_header_seconds",
            "trace_event_seconds", "cpu_units", "scheduling", "file_durations",
            "hook_roles", "events_lost", "buffers_lost"}
    keys |= {"root_cpu_samples", "descendant_cpu_samples", "lifetimes", "images"}
    if set(value) != keys:
        raise ValueError("public_schema")
    enums = {"status": {"PARTIAL"}, "cpu_units": {"SAMPLE_COUNTS"},
             "scheduling": {"UNSUPPORTED"}, "file_durations": {"UNSUPPORTED"},
             "hook_roles": {"UNKNOWN"}}
    for k, v in value.items():
        if k in enums:
            if v not in enums[k]:
                raise ValueError("public_enum")
        elif k == "lifetimes":
            if not isinstance(v, list) or not 1 <= len(v) <= 128:
                raise ValueError("public_lifetimes")
            for index, row in enumerate(v):
                if set(row) != {"role", "parent_index", "start_seconds", "end_seconds", "cpu_samples", "file_operation_records"} or row["role"] not in {"ROOT", "UNKNOWN_DESCENDANT"}:
                    raise ValueError("public_lifetime")
                if any(type(row[f]) is not int or not 0 <= row[f] <= 1e12
                       for f in ("cpu_samples", "file_operation_records")):
                    raise ValueError("public_lifetime_counts")
                if any(type(row[f]) not in (int, float) or not math.isfinite(row[f]) or not 0 <= row[f] <= 20
                       for f in ("start_seconds", "end_seconds")) or row["end_seconds"] < row["start_seconds"]:
                    raise ValueError("public_lifetime_time")
                parent = row["parent_index"]
                if index == 0:
                    if parent is not None or row["role"] != "ROOT":
                        raise ValueError("public_parent_graph")
                elif type(parent) is not int or not 0 <= parent < index or row["role"] != "UNKNOWN_DESCENDANT":
                    raise ValueError("public_parent_graph")
                elif not v[parent]["start_seconds"] <= row["start_seconds"] <= row["end_seconds"] <= v[parent]["end_seconds"]:
                    raise ValueError("public_parent_time")
        elif k == "images":
            if not isinstance(v, list) or len(v) > 256:
                raise ValueError("public_images")
            for row in v:
                if set(row) != {"process_index", "module", "checksum", "timestamp", "size_bytes"} or row["module"] not in MODULES:
                    raise ValueError("public_image")
                if any(type(row[f]) is not int or not 0 <= row[f] <= 2**40
                       for f in ("process_index", "checksum", "timestamp", "size_bytes")):
                    raise ValueError("public_image_number")
        elif k == "modules":
            if not isinstance(v, list) or len(v) > len(MODULES) + 1:
                raise ValueError("public_modules")
            for row in v:
                if set(row) != {"module", "samples", "fraction"} or row["module"] not in MODULES | {"unresolved"}:
                    raise ValueError("public_module")
                if (type(row["samples"]) is not int or not 1 <= row["samples"] <= 1e12
                        or type(row["fraction"]) not in (int, float) or not math.isfinite(row["fraction"])
                        or not 0 <= row["fraction"] <= 1):
                    raise ValueError("public_sample")
        elif type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1e12:
            raise ValueError("public_number")
    if len(json.dumps(value, allow_nan=False)) > 65536:
        raise ValueError("public_size")
    if (value["schema"] != 1 or value["events_lost"] != 0 or value["buffers_lost"] != 0
            or value["family_lifetimes"] != len(value["lifetimes"])
            or value["cpu_samples"] != sum(r["samples"] for r in value["modules"])
            or value["cpu_samples"] != value["root_cpu_samples"] + value["descendant_cpu_samples"]
            or value["cpu_samples"] != sum(r["cpu_samples"] for r in value["lifetimes"])
            or value["file_operation_records"] != sum(r["file_operation_records"] for r in value["lifetimes"])
            or value["root_cpu_samples"] != value["lifetimes"][0]["cpu_samples"]
            or value["cpu_samples"] < 1 or value["file_operation_records"] < 1
            or value["unresolved_samples"] != sum(r["samples"] for r in value["modules"] if r["module"] == "unresolved")):
        raise ValueError("public_consistency")
    if any(abs(row["fraction"] - row["samples"] / value["cpu_samples"]) > 1e-12 for row in value["modules"]):
        raise ValueError("public_fraction")
    if any(row["process_index"] >= value["family_lifetimes"] for row in value["images"]):
        raise ValueError("public_image_owner")
