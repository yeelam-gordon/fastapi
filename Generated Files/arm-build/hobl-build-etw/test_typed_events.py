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
