"""Strict private TraceEvent DTO adapter. Source version/opcode are never rewritten."""
import json
import re

KEYS = {"schema", "kind", "sourceType", "provider", "eventId", "version", "opcode",
        "qpc", "pid", "tid", "processBirthQpc", "payload"}
PAYLOADS = {
    "header": {"perfFreq", "reservedFlags", "eventsLost", "buffersLost",
               "sessionStartFileTime", "sessionEndFileTime", "lastQpc"},
    **{k: {"parentPid"} for k in ("processStart", "processStop", "processDCStart", "processDCStop")},
    **{k: set() for k in ("threadStart", "threadStop", "threadDCStart", "threadDCStop", "readyThread")},
    **{k: {"imageBase", "imageSize", "fileName"} for k in ("imageLoad", "imageUnload", "imageDCStart", "imageDCStop")},
    "sample": {"instructionPointer"}, "fileCreate": {"irp", "fileObject", "fileName"},
    "fileRead": {"irp", "fileObject", "fileKey", "sizeBytes"},
    "fileWrite": {"irp", "fileObject", "fileKey", "sizeBytes"},
    "fileOpEnd": {"irp"}, "cswitch": {"oldTid", "newTid"},
}
TYPES = {
    **{k: "ProcessTraceData" for k in PAYLOADS if k.startswith("process")},
    **{k: "ThreadTraceData" for k in PAYLOADS if k.startswith("thread")},
    **{k: "ImageLoadTraceData" for k in PAYLOADS if k.startswith("image")},
    "header": "EventTraceHeaderTraceData", "sample": "SampledProfileTraceData",
    "fileCreate": "FileIOCreateTraceData", "fileRead": "FileIOReadWriteTraceData",
    "fileWrite": "FileIOReadWriteTraceData", "fileOpEnd": "FileIOOpEndTraceData",
    "cswitch": "CSwitchTraceData", "readyThread": "DispatcherReadyThreadTraceData",
}
PAYLOADS_V2 = {
    **PAYLOADS,
    "fileOpEnd": {"irp", "extraInfo", "ntStatus"},
    "cswitch": {"oldTid", "newTid", "oldThreadState", "oldThreadWaitReason",
                "oldThreadWaitMode", "processorNumber"},
    "readyThread": {"awakenedTid", "adjustReason", "adjustIncrement", "flags",
                    "processorNumber"},
}
V2_RANGES = {
    "oldTid": (-1, 2**31 - 1), "newTid": (-1, 2**31 - 1),
    "awakenedTid": (0, 2**31 - 1), "oldThreadState": (0, 255),
    "oldThreadWaitReason": (0, 255), "oldThreadWaitMode": (0, 255),
    "processorNumber": (0, 2**16 - 1), "adjustReason": (0, 255),
    "adjustIncrement": (0, 255), "flags": (0, 255), "ntStatus": (0, 2**32 - 1),
}


def integer(value, low=0, high=2**64 - 1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("schema")
    return value


def rows(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if len(line) > 65536:
                raise ValueError("schema")
            row = json.loads(line)
            if (not isinstance(row, dict) or set(row) != KEYS
                    or type(row["schema"]) is not int or row["schema"] not in (1, 2)
                    or row["kind"] not in PAYLOADS or row["sourceType"] != TYPES[row["kind"]]):
                raise ValueError("schema")
            payload_keys = (PAYLOADS if row["schema"] == 1 else PAYLOADS_V2)[row["kind"]]
            if not isinstance(row["provider"], str) or re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", row["provider"]) is None:
                raise ValueError("schema")
            for key, maximum in (("eventId", 65535), ("version", 255), ("opcode", 255)):
                integer(row[key], 0, maximum)
            integer(row["qpc"], 0, 2**63 - 1)
            for key in ("pid", "tid"):
                if row["kind"] != "header":
                    integer(row[key], -1, 2**31 - 1)
                elif row[key] is not None:
                    raise ValueError("schema")
            if row["processBirthQpc"] is not None:
                integer(row["processBirthQpc"], 0, 2**63 - 1)
            payload = row["payload"]
            if payload is None and not payload_keys:
                payload = {}
            if not isinstance(payload, dict) or set(payload) != payload_keys:
                raise ValueError("schema")
            for key, value in payload.items():
                if key == "fileName":
                    if not isinstance(value, str) or len(value) > 32768:
                        raise ValueError("schema")
                else:
                    limits = V2_RANGES.get(key) if row["schema"] == 2 else None
                    if limits is not None:
                        integer(value, *limits)
                    else:
                        integer(value, -1 if key in {"parentPid", "oldTid", "newTid"} else 0)
            row["payload"] = payload
            yield row


def events(path):
    for row in rows(path):
        k, p = row["kind"], row["payload"]
        if ((k.startswith("thread") and (row["pid"] < 0 or row["tid"] < 0))
                or (k in {"sample", "fileCreate", "fileRead", "fileWrite"} and row["tid"] < 0)):
            continue
        data = {}
        if k == "header":
            data = dict(PerfFreq=p["perfFreq"], ReservedFlags=p["reservedFlags"],
                        EventsLost=p["eventsLost"], BuffersLost=p["buffersLost"],
                        StartTime=p["sessionStartFileTime"], EndTime=p["sessionEndFileTime"])
        elif k.startswith("process"):
            data = dict(ProcessId=row["pid"], ParentId=p["parentPid"])
        elif k.startswith("thread"):
            data = dict(ProcessId=row["pid"], TThreadId=row["tid"])
        elif k.startswith("image"):
            data = dict(ProcessId=row["pid"], ImageBase=p["imageBase"],
                        ImageSize=p["imageSize"], FileName=p["fileName"])
        elif k == "sample":
            data = dict(ThreadId=row["tid"], InstructionPointer=p["instructionPointer"])
        elif k in {"fileCreate", "fileRead", "fileWrite"}:
            data = dict(IssuingThreadId=row["tid"], Irp=p["irp"], FileObject=p["fileObject"])
            if "fileName" in p:
                data["FileName"] = p["fileName"]
        elif k == "fileOpEnd":
            data = {"Irp": p["irp"]}
            if row["schema"] == 2:
                data.update(ExtraInfo=p["extraInfo"], NtStatus=p["ntStatus"])
        elif k == "cswitch":
            data = dict(OldThreadId=p["oldTid"], NewThreadId=p["newTid"])
            if row["schema"] == 2:
                data.update(OldThreadState=p["oldThreadState"],
                            OldThreadWaitReason=p["oldThreadWaitReason"],
                            OldThreadWaitMode=p["oldThreadWaitMode"],
                            ProcessorNumber=p["processorNumber"])
        elif k == "readyThread" and row["schema"] == 2:
            data = dict(AwakenedThreadId=p["awakenedTid"], AdjustReason=p["adjustReason"],
                        AdjustIncrement=p["adjustIncrement"], Flags=p["flags"],
                        ProcessorNumber=p["processorNumber"])
        yield dict(kind=k, name="", data=data, qpc=row["qpc"], version=row["version"],
                   opcode=row["opcode"], id=row["eventId"], provider="{" + row["provider"].lower() + "}",
                   tid=row["tid"], source_type=row["sourceType"],
                   last_qpc=p.get("lastQpc") if k == "header" else None)


def proof(path):
    schemas, header = set(), None
    for row in rows(path):
        schemas.add((row["kind"], row["sourceType"], row["provider"], row["eventId"],
                     row["version"], row["opcode"], tuple(sorted(row["payload"]))))
        if len(schemas) > 128:
            raise ValueError("schema")
        if row["kind"] == "header":
            p = row["payload"]
            header = {k: p[k] for k in ("perfFreq", "reservedFlags", "eventsLost", "buffersLost")}
    if header is None:
        raise ValueError("schema")
    return {"schema": 1, "library": "Microsoft.Diagnostics.Tracing.TraceEvent",
            "version": "4.0.0", "header": header,
            "schemas": [{"kind": k, "source_type": t, "provider": p, "event_id": i,
                         "version": v, "opcode": o, "fields": list(f)}
                        for k, t, p, i, v, o, f in sorted(schemas)]}
