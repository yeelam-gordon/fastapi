import copy
import json
from pathlib import Path
import shutil
import unittest
import uuid

import decode
import typed_events
import capture


def row(kind, qpc, pid=10, tid=11, payload=None, version=3, opcode=1):
    source = ("EventTraceHeaderTraceData" if kind == "header" else
              "ProcessTraceData" if kind.startswith("process") else
              "ThreadTraceData" if kind.startswith("thread") else
              "ImageLoadTraceData" if kind.startswith("image") else
              "SampledProfileTraceData" if kind == "sample" else "FileIOCreateTraceData")
    return dict(schema=1, kind=kind, sourceType=source, provider=decode.KERNEL[1:-1],
                eventId=65535, version=version, opcode=opcode, qpc=qpc, pid=pid, tid=tid,
                processBirthQpc=None, payload=payload)


class Typed(unittest.TestCase):
    def setUp(self):
        self.folder = Path(__file__).parent / ("test-private-" + uuid.uuid4().hex)
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = self.folder / "dto.jsonl"

    def write(self, records):
        self.path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    def records(self):
        records = []
        for pid, tid, birth, base in ((10, 11, 100, 4096), (20, 21, 120, 8192)):
            records.extend([
                row("processStart", birth, pid, tid, {"parentPid": 1 if pid == 10 else 10}, 4),
                row("threadStart", birth + 1, pid, tid),
                row("imageLoad", birth + 2, pid, tid,
                    {"imageBase": base, "imageSize": 100, "fileName": r"C:\PRIVATE\python.exe"}, 3, 10),
                row("sample", birth + 3, pid, tid, {"instructionPointer": base + 10}, 2, 46),
                row("fileCreate", birth + 4, pid, tid,
                    {"irp": base, "fileObject": base + 1, "fileName": r"C:\PRIVATE\calibration-data.bin"}),
                row("processStop", 200 if pid == 10 else 180, pid, tid, {"parentPid": 1 if pid == 10 else 10}, 4, 2),
            ])
        records.sort(key=lambda r: r["qpc"])
        records.append(row("header", 90, None, None, dict(
            perfFreq=10000000, reservedFlags=1, eventsLost=0, buffersLost=0,
            sessionStartFileTime=0, sessionEndFileTime=10000000, lastQpc=201), 2, 0))
        return records

    def test_semantic_v3_image_and_activity_gates(self):
        self.write(self.records())
        anchor = dict(pid=10, qpc_before=99, qpc_after=101, qpc_end=201,
                      creation_filetime=1000, filetime_after=1000, qpc_frequency=10000000)
        child = dict(anchor, pid=20, qpc_before=119, qpc_after=121, qpc_end=181)
        result = decode.analyze(self.path, anchor, True, child, typed_events.events)
        self.assertEqual([r["cpu_samples"] for r in result["lifetimes"]], [1, 1])
        self.assertEqual([r["file_operation_records"] for r in result["lifetimes"]], [1, 1])
        self.assertEqual(result["images"][0]["module"], "python.exe")
        self.assertIsNone(result["images"][0]["checksum"])
        proof = typed_events.proof(self.path)
        self.assertNotIn("PRIVATE", json.dumps(proof))
        self.assertTrue(any(r["kind"] == "imageLoad" and r["version"] == 3 for r in proof["schemas"]))
        records = [r for r in self.records() if not (r["kind"] == "fileCreate" and r["pid"] == 20)]
        self.write(records)
        with self.assertRaisesRegex(ValueError, "insufficient_owned_evidence"):
            decode.analyze(self.path, anchor, True, child, typed_events.events)
        records = self.records()
        records[0]["kind"] = "processDCStart"
        self.write(records)
        with self.assertRaisesRegex(ValueError, "root_birth_window"):
            decode.analyze(self.path, anchor, event_reader=typed_events.events)
        records = self.records()
        records[1]["tid"] = -1
        self.write(records)
        with self.assertRaisesRegex(ValueError, "insufficient_owned_evidence"):
            decode.analyze(self.path, anchor, True, child, typed_events.events)

    def test_missing_dotnet_is_explicit_before_capture(self):
        controller = capture.Controller(self.folder, self.folder / "public", self.folder, Path("uv"))
        controller.dotnet = None
        with self.assertRaises(capture.Failure) as failure:
            controller.prepare_reader()
        self.assertEqual(controller.stage, "reader_prepare")
        self.assertEqual(failure.exception.reason, "missing_dotnet10")

    def test_scheduling_and_completion_payloads_survive_adapter(self):
        records = [
            dict(row("readyThread", 100, tid=11, version=2, opcode=50),
                 schema=2, sourceType="DispatcherReadyThreadTraceData",
                 payload=dict(awakenedTid=99, adjustReason=2, adjustIncrement=3,
                              flags=4, processorNumber=5)),
            dict(row("cswitch", 101, tid=99, version=5, opcode=36),
                 schema=2, sourceType="CSwitchTraceData",
                 payload=dict(oldTid=11, newTid=99, oldThreadState=5,
                              oldThreadWaitReason=6, oldThreadWaitMode=1, processorNumber=5)),
            dict(row("fileOpEnd", 102, version=3, opcode=76),
                 schema=2, sourceType="FileIOOpEndTraceData",
                 payload=dict(irp=2**64 - 1, extraInfo=2**63 + 7, ntStatus=0xC0000001)),
        ]
        self.write(records)
        events = list(typed_events.events(self.path))
        self.assertEqual(events[0]["tid"], 11)
        self.assertEqual(events[0]["data"], dict(
            AwakenedThreadId=99, AdjustReason=2, AdjustIncrement=3, Flags=4, ProcessorNumber=5))
        self.assertEqual(events[1]["data"], dict(
            OldThreadId=11, NewThreadId=99, OldThreadState=5,
            OldThreadWaitReason=6, OldThreadWaitMode=1, ProcessorNumber=5))
        self.assertEqual(events[2]["data"], dict(
            Irp=2**64 - 1, ExtraInfo=2**63 + 7, NtStatus=0xC0000001))
        for record, event in zip(records, events):
            for source, target in (("qpc", "qpc"), ("version", "version"),
                                   ("opcode", "opcode"), ("eventId", "id")):
                self.assertEqual(event[target], record[source])
            self.assertEqual(event["provider"], "{" + record["provider"] + "}")
        for index, field, value in ((0, "awakenedTid", None), (0, "flags", True),
                                    (0, "adjustIncrement", 256), (1, "oldThreadState", -1),
                                    (2, "ntStatus", 2**32), (2, "irp", 2**64)):
            malformed = copy.deepcopy(records)
            malformed[index]["payload"][field] = value
            self.write(malformed)
            with self.assertRaisesRegex(ValueError, "schema"):
                list(typed_events.events(self.path))
        for payload in (None, {}, dict(records[0]["payload"], unexpected=1)):
            malformed = copy.deepcopy(records)
            malformed[0]["payload"] = payload
            self.write(malformed)
            with self.assertRaisesRegex(ValueError, "schema"):
                list(typed_events.events(self.path))

    def test_legacy_payloads_remain_legacy_and_v2_analysis_matches(self):
        legacy = [
            dict(row("readyThread", 100), sourceType="DispatcherReadyThreadTraceData"),
            dict(row("cswitch", 101), sourceType="CSwitchTraceData",
                 payload=dict(oldTid=11, newTid=99)),
            dict(row("fileOpEnd", 102), sourceType="FileIOOpEndTraceData", payload=dict(irp=123)),
        ]
        self.write(legacy)
        self.assertEqual([event["data"] for event in typed_events.events(self.path)],
                         [{}, dict(OldThreadId=11, NewThreadId=99), dict(Irp=123)])
        self.assertTrue(all(record["schema"] == 1 for record in typed_events.rows(self.path)))
        anchor = dict(pid=10, qpc_before=99, qpc_after=101, qpc_end=201,
                      creation_filetime=1000, filetime_after=1000, qpc_frequency=10000000)
        self.write(self.records())
        original = decode.analyze(self.path, anchor, event_reader=typed_events.events)
        enriched = [dict(record, schema=2) for record in self.records()]
        enriched.extend([
            dict(row("readyThread", 150, tid=11, version=2, opcode=50),
                 schema=2, sourceType="DispatcherReadyThreadTraceData",
                 payload=dict(awakenedTid=21, adjustReason=0, adjustIncrement=0,
                              flags=0, processorNumber=0)),
            dict(row("cswitch", 151, tid=21, version=5, opcode=36),
                 schema=2, sourceType="CSwitchTraceData",
                 payload=dict(oldTid=11, newTid=21, oldThreadState=5,
                              oldThreadWaitReason=6, oldThreadWaitMode=1, processorNumber=0)),
            dict(row("fileOpEnd", 152, pid=999, tid=888, version=3, opcode=76),
                 schema=2, sourceType="FileIOOpEndTraceData",
                 payload=dict(irp=4096, extraInfo=0, ntStatus=0xC0000001)),
        ])
        self.write(sorted(enriched, key=lambda record: record["qpc"]))
        self.assertEqual(decode.analyze(self.path, anchor, event_reader=typed_events.events), original)

    def test_malformed_and_private_field_rejection(self):
        good = self.records()
        for mutate in (
            lambda r: r[0].update(commandLine="PRIVATE"),
            lambda r: r[-1]["payload"].update(perfFreq=None),
            lambda r: r[1].update(tid=None),
            lambda r: r[0].update(sourceType="PRIVATE"),
        ):
            records = copy.deepcopy(good)
            mutate(records)
            self.write(records)
            with self.assertRaises((ValueError, KeyError)):
                list(typed_events.events(self.path))


if __name__ == "__main__":
    unittest.main()
