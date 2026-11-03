"""Bounded schema-only sidecar; no event payload values or activity counts."""
import json
import re
import xml.etree.ElementTree as ET

NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"
TRACE = "{http://schemas.microsoft.com/win/2004/08/events/trace}"
KERNEL = "{9e814aad-3204-11d2-9a82-006008a86939}"
LABELS = {"EventTrace", "Process", "Thread", "Image", "PerfInfo", "FileIo", "DiskIo", "StackWalk", "OTHER"}
HEADER = {"PerfFreq", "ReservedFlags", "EventsLost", "BuffersLost", "PointerSize"}
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}", re.ASCII)
GUID = re.compile(r"\{[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}", re.ASCII)
REASONS = {"NONE", "METADATA_REJECTED", "CAPACITY", "XML_PARSE"}


def uint(text, maximum):
    value = str(text).strip()
    if not re.fullmatch(r"(?:[0-9]{1,20}|0x[0-9a-fA-F]{1,16})", value, re.ASCII):
        raise ValueError("metadata")
    result = int(value, 16 if value.startswith("0x") else 10)
    if not 0 <= result <= maximum:
        raise ValueError("metadata")
    return result


def names(values):
    result = sorted(set(values))
    if len(result) > 64 or any(type(v) is not str or NAME.fullmatch(v) is None for v in result):
        raise ValueError("metadata")
    return result


def validate(value):
    if set(value) != {"schema", "status", "reason", "header", "schemas"} or value["schema"] != 1:
        raise ValueError("metadata")
    if value["status"] not in {"COMPLETE", "PARTIAL"} or value["reason"] not in REASONS:
        raise ValueError("metadata")
    if set(value["header"]) != HEADER or len(value["schemas"]) > 128:
        raise ValueError("metadata")
    for v in value["header"].values():
        if v is not None and (type(v) is not int or not 0 <= v <= 2**63 - 1):
            raise ValueError("metadata")
    for row in value["schemas"]:
        if set(row) != {"provider", "event_id", "version", "opcode", "task_label", "time_attributes", "fields"}:
            raise ValueError("metadata")
        if row["provider"] != "OTHER" and GUID.fullmatch(row["provider"]) is None:
            raise ValueError("metadata")
        if row["task_label"] not in LABELS:
            raise ValueError("metadata")
        for field, maximum in (("event_id", 65535), ("version", 255), ("opcode", 255)):
            if type(row[field]) is not int or not 0 <= row[field] <= maximum:
                raise ValueError("metadata")
        for key in ("time_attributes", "fields"):
            if type(row[key]) is not list or row[key] != names(row[key]):
                raise ValueError("metadata")
    if len(json.dumps(value, allow_nan=False).encode("ascii")) > 2 * 1024**2:
        raise ValueError("metadata")


def extract(path):
    result = {"schema": 1, "status": "COMPLETE", "reason": "NONE",
              "header": {k: None for k in sorted(HEADER)}, "schemas": []}
    seen = set()
    def partial(reason):
        result["status"], result["reason"] = "PARTIAL", reason
    try:
        context = ET.iterparse(path, events=("start", "end"))
        _, root = next(context)
        for action, element in context:
            if action != "end" or element.tag != NS + "Event":
                continue
            try:
                system = element.find(NS + "System")
                provider = system.find(NS + "Provider").get("Guid", "").lower()
                if GUID.fullmatch(provider) is None:
                    provider = "OTHER"
                rendered = element.findtext(".//" + TRACE + "EventName", "")
                label = rendered if rendered in LABELS else "OTHER"
                time = system.find(NS + "TimeCreated")
                data = element.findall(NS + "EventData/" + NS + "Data")
                row = {"provider": provider,
                       "event_id": uint(system.findtext(NS + "EventID"), 65535),
                       "version": uint(system.findtext(NS + "Version"), 255),
                       "opcode": uint(system.findtext(NS + "Opcode"), 255),
                       "task_label": label,
                       "time_attributes": names(time.attrib if time is not None else ()),
                       "fields": names(item.get("Name") for item in data)}
                encoded = json.dumps(row, sort_keys=True)
                if encoded not in seen:
                    if len(result["schemas"]) < 128:
                        seen.add(encoded)
                        result["schemas"].append(row)
                    else:
                        partial("CAPACITY")
                if provider == KERNEL and label == "EventTrace" and row["event_id"] == 0:
                    for item in data:
                        key = item.get("Name")
                        if key in HEADER:
                            result["header"][key] = uint(item.text, 2**63 - 1)
            except (ValueError, TypeError, AttributeError):
                partial("METADATA_REJECTED")
            element.clear()
            root.clear()
    except (ET.ParseError, StopIteration):
        partial("XML_PARSE")
    validate(result)
    return result
