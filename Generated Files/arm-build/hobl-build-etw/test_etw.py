import copy
import json
import os
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch
from types import SimpleNamespace

import capture
import decode


class Proof(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).parent / ("test-private-" + uuid.uuid4().hex)
        self.path.mkdir()
        self.addCleanup(shutil.rmtree, self.path)

    def test_family_pid_reuse_and_native_clock(self):
        lives = [dict(pid=10, parent=1, start=100, end=200),
                 dict(pid=20, parent=10, start=150, end=190),
                 dict(pid=10, parent=1, start=300, end=400),
                 dict(pid=21, parent=10, start=350, end=390)]
        anchor = dict(pid=10, qpc_before=99, qpc_after=101,
                      creation_filetime=1000000, filetime_after=1000000)
        self.assertEqual(len(decode.family(lives, anchor, 10000000)), 2)
        anchor["creation_filetime"] = 100000000
        with self.assertRaises(ValueError):
            decode.family(lives, anchor, 10000000)

    def test_public_schema_poison(self):
        good = dict(schema=1, status="PARTIAL", family_lifetimes=1, cpu_samples=1,
                    root_cpu_samples=1, descendant_cpu_samples=0,
                    lifetimes=[dict(role="ROOT", parent_index=None, start_seconds=0, end_seconds=1,
                                    cpu_samples=1, file_operation_records=1)], images=[],
                    file_operation_records=1, unresolved_samples=0,
                    modules=[dict(module="uv.exe", samples=1, fraction=1)],
                    interval_seconds=1, trace_header_seconds=1, trace_event_seconds=2,
                    cpu_units="SAMPLE_COUNTS", scheduling="UNSUPPORTED",
                    file_durations="UNSUPPORTED", hook_roles="UNKNOWN",
                    events_lost=0, buffers_lost=0)
        decode.validate(good)
        for field in ("commandline", "path", "error", "sid", "foreign_pid"):
            bad = dict(good, **{field: "PRIVATE_SENTINEL"})
            with self.assertRaises(ValueError):
                decode.validate(bad)
        for number in (float("nan"), float("inf"), -1, "PRIVATE_SENTINEL"):
            bad = dict(good, interval_seconds=number)
            with self.assertRaises(ValueError):
                decode.validate(bad)
        bad = copy.deepcopy(good)
        bad["modules"][0]["module"] = r"C:\PRIVATE\python.exe"
        with self.assertRaises(ValueError):
            decode.validate(bad)

    def test_native_failure_and_owned_cleanup_only(self):
        calls = []
        def fake(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(succeeded=False, returncode=-123)
        c = capture.Controller(self.path, self.path / "public", self.path, Path("uv"), fake)
        c.stage = "build_stop"
        with self.assertRaises(capture.Failure) as failure:
            c.command("wpr", ["wpr", "-stop", "private.etl"], 60)
        self.assertEqual(failure.exception.code, -123)
        c.cleanup()
        self.assertEqual(len(calls), 1)
        c.owned = "hobl-build-unique"
        with self.assertRaises(capture.Failure):
            c.cleanup()
        self.assertEqual(calls[-1][-2:], ["-instancename", "hobl-build-unique"])
        self.assertNotIn(["wpr", "-cancel"], calls)
        self.assertEqual(c.owned, "hobl-build-unique")
        c.report("wpr", -123, "FAILED")
        value = json.loads((c.public / "stage.json").read_text())
        self.assertEqual(value["native_code"], -123)
        self.assertTrue(value["residual_buffers_possible"])

    def test_local_gate_and_skipped_jobs(self):
        with self.assertRaises(capture.Failure):
            capture.hosted_gate({})
        env = dict(GITHUB_ACTIONS="true", GITHUB_REPOSITORY="yeelam-gordon/fastapi",
                   GITHUB_RUN_ATTEMPT="1", RUNNER_ENVIRONMENT="github-hosted",
                   RUNNER_OS="Windows", RUNNER_ARCH="ARM64",
                   GITHUB_REF="refs/heads/perf/hobl-build-etw-20261103",
                   GITHUB_RUN_ID="42", GITHUB_SHA="a" * 40, RUNNER_NAME="host")
        run = dict(head_sha=env["GITHUB_SHA"], head_branch="perf/hobl-build-etw-20261103",
                   workflow_id=400482741, run_attempt=1, event="workflow_dispatch")
        jobs = dict(total_count=2, jobs=[
            dict(status="in_progress", conclusion=None, name="build-etw / trace",
                 runner_name="host", labels=["windows-11-arm"]),
            dict(status="completed", conclusion="skipped")])
        capture.hosted_gate(env, lambda suffix: jobs if "/jobs?" in suffix else run)
        jobs["jobs"].append(dict(status="queued", conclusion=None))
        with self.assertRaises(capture.Failure):
            capture.hosted_gate(env, lambda suffix: jobs if "/jobs?" in suffix else run)

    def test_graph_reasons_and_artifact_gate(self):
        self.assertEqual(capture.safe_reason(ValueError("root_birth_window")), "root_birth_window")
        self.assertEqual(capture.safe_reason(ValueError(r"C:\PRIVATE")), "schema")
        anchor = dict(pid=10, qpc_before=99, qpc_after=101,
                      creation_filetime=1000, filetime_after=1000)
        lives = [dict(pid=10, parent=1, start=100, end=500),
                 dict(pid=20, parent=10, start=110, end=120),
                 dict(pid=20, parent=10, start=130, end=140)]
        with self.assertRaisesRegex(ValueError, "duplicate_owned_pid"):
            decode.family(lives, anchor, 10000000)
        c = capture.Controller(self.path, self.path / "public", self.path, Path("uv"))
        with patch.dict("sys.modules", {"screen": SimpleNamespace(source_snapshot=lambda source: {"a": "digest"})}):
            with patch.object(capture, "artifact_set", return_value={"validated": True}) as gate, \
                 patch.object(capture, "equivalent") as compare:
                c.check_artifacts()
                self.assertEqual(c.stage, "build_artifacts")
                self.assertEqual(gate.call_count, 2)
                self.assertEqual(gate.call_args.args[2], {"a": "digest"})
                compare.assert_called_once_with({"validated": True}, {"validated": True})
            with patch.object(capture, "artifact_set", return_value={}), \
                 patch.object(capture, "equivalent", side_effect=ValueError("metadata differs")):
                with self.assertRaises(capture.Failure) as failure:
                    c.check_artifacts()
                self.assertEqual(failure.exception.reason, "artifacts")
            with patch.object(capture, "artifact_set", side_effect=RuntimeError("PRIVATE")):
                with self.assertRaises(capture.Failure) as failure:
                    c.check_artifacts()
                self.assertEqual(failure.exception.reason, "artifacts")

    def test_stop_failure_cancels_only_successfully_started_instance(self):
        calls = []
        def fake(argv, **kwargs):
            calls.append(argv)
            failed = "-stop" in argv
            return SimpleNamespace(succeeded=not failed, returncode=-456 if failed else 0)
        c = capture.Controller(self.path, self.path / "public", self.path, Path("uv"), fake)
        with self.assertRaises(capture.Failure) as failure:
            c.trace("build", ["uv", "build"], {})
        self.assertEqual(failure.exception.code, -456)
        start, launch, stop, cancel = calls
        self.assertIn("-start", start)
        self.assertIn("-stop", stop)
        self.assertIn("-cancel", cancel)
        self.assertEqual(start[-1], stop[-1])
        self.assertEqual(stop[-1], cancel[-1])
        self.assertEqual(c.stage, "build_stop")
        self.assertIsNone(c.owned)
        self.assertFalse(c.residual)

    def test_capture_proof_retained_when_analysis_fails(self):
        def fake(argv, **kwargs):
            if "-stop" in argv:
                Path(argv[2]).write_bytes(b"PRIVATE_ETL_BYTES")
            return SimpleNamespace(succeeded=True, returncode=0)
        c = capture.Controller(self.path, self.path / "public", self.path, Path("uv"), fake)
        with self.assertRaises(FileNotFoundError):
            c.trace("build", ["uv", "build"], {})
        proof = json.loads((c.public / "capture-proof.json").read_text())
        self.assertEqual(set(proof), {"schema", "calibration", "build"})
        self.assertIsNone(proof["calibration"])
        self.assertEqual(set(proof["build"]), {"etl_sha256", "bytes", "profile_sha256"})
        self.assertEqual(proof["build"]["bytes"], 17)
        self.assertNotIn("PRIVATE_ETL_BYTES", json.dumps(proof))
        c.report("controller", -1, "FAILED", "schema")
        self.assertTrue((c.public / "capture-proof.json").is_file())

    def test_failed_start_is_not_cancel_authority(self):
        calls = []
        def fake(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(succeeded=False, returncode=-789)
        c = capture.Controller(self.path, self.path / "public", self.path, Path("uv"), fake)
        with self.assertRaises(capture.Failure):
            c.trace("build", ["uv", "build"], {})
        self.assertEqual(len(calls), 1)
        self.assertTrue(c.residual)
        self.assertIsNone(c.owned)
        c.cleanup()
        self.assertEqual(len(calls), 1)

    def test_stream_decode_owned_counts_not_rundown(self):
        ns = decode.NS[1:-1]
        def event(name, q, version, opcode, data, tid=0, provider=decode.KERNEL, eid=0):
            fields = "".join(f'<Data Name="{k}">{v}</Data>' for k, v in data.items())
            return (f'<Event xmlns="{ns}"><System><Provider Guid="{provider}"/>'
                    f'<EventID>{eid}</EventID><Version>{version}</Version><Opcode>{opcode}</Opcode>'
                    f'<TimeCreated RawTime="{q}"/><Execution ThreadID="{tid}"/></System>'
                    f'<EventData>{fields}</EventData><RenderingInfo><EventName xmlns="{decode.TRACE[1:-1]}">'
                    f'{name}</EventName></RenderingInfo></Event>')
        child_sample = event("PerfInfo", 130, 2, 46, dict(ThreadId=21, InstructionPointer=8200))
        content = [
            event("EventTrace", 90, 2, 0, dict(PerfFreq=10000000, ReservedFlags=1,
                   EventsLost=0, BuffersLost=0, StartTime=0, EndTime=10000000)),
            event("Process", 100, 4, 1, dict(ProcessId=10, ParentId=1)),
            event("Thread", 101, 3, 1, dict(ProcessId=10, TThreadId=11)),
            event("Image", 102, 2, 10, dict(ProcessId=10, ImageBase=4096, ImageSize=100, FileName="uv.exe")),
            event("PerfInfo", 110, 2, 46, dict(ThreadId=11, InstructionPointer=4100)),
            event("FileIo", 111, 2, 36, dict(FileObject=1, FileName="PRIVATE")),
            event("", 112, 1, 0, dict(IssuingThreadId=11, Irp=1, FileObject=1, FileName=r"C:\owned\calibration-data.bin"),
                  provider="{edd08927-9cc4-4e65-b970-c2560fb5c289}", eid=12),
            event("Process", 120, 4, 1, dict(ProcessId=20, ParentId=10)),
            event("Thread", 121, 3, 1, dict(ProcessId=20, TThreadId=21)),
            event("Image", 122, 2, 10, dict(ProcessId=20, ImageBase=8192, ImageSize=100, FileName="python313.dll")),
            child_sample,
            event("", 132, 1, 0, dict(IssuingThreadId=21, Irp=2, FileObject=2, FileName=r"C:\owned\child\calibration-data.bin"),
                  provider="{edd08927-9cc4-4e65-b970-c2560fb5c289}", eid=12),
            event("Process", 180, 4, 2, dict(ProcessId=20)),
            event("Process", 200, 4, 2, dict(ProcessId=10)),
        ]
        xml = self.path / "events.xml"
        document = "<Events>" + "".join(content) + "</Events>"
        xml.write_text(document)
        anchor = dict(pid=10, qpc_before=99, qpc_after=101, qpc_end=201,
                      creation_filetime=1000, filetime_after=1000, qpc_frequency=10000000)
        result = decode.analyze(xml, anchor)
        self.assertEqual(result["cpu_samples"], 2)
        self.assertEqual(result["file_operation_records"], 2)
        self.assertEqual({row["module"]: row["samples"] for row in result["modules"]},
                         {"uv.exe": 1, "python313.dll": 1})
        self.assertEqual([x["parent_index"] for x in result["lifetimes"]], [None, 0])
        self.assertEqual([x["cpu_samples"] for x in result["lifetimes"]], [1, 1])
        self.assertEqual([x["file_operation_records"] for x in result["lifetimes"]], [1, 1])
        poisoned = copy.deepcopy(result)
        poisoned["lifetimes"][1]["parent_index"] = 1
        with self.assertRaisesRegex(ValueError, "public_parent_graph"):
            decode.validate(poisoned)
        poisoned = copy.deepcopy(result)
        poisoned["lifetimes"][1]["end_seconds"] = 1
        with self.assertRaisesRegex(ValueError, "public_parent_time"):
            decode.validate(poisoned)
        child_anchor = dict(pid=20, qpc_before=119, qpc_after=121, qpc_end=181,
                            creation_filetime=1000, filetime_after=1000, qpc_frequency=10000000)
        decode.analyze(xml, anchor, calibration=True, child_anchor=child_anchor)
        xml.write_text(document.replace(child_sample, ""))
        with self.assertRaisesRegex(ValueError, "insufficient_owned_evidence"):
            decode.analyze(xml, anchor, calibration=True, child_anchor=child_anchor)
        xml.write_text(document)
        xml.write_text(xml.read_text().replace('Name="EventsLost">0', 'Name="EventsLost">1'))
        with self.assertRaises(ValueError):
            decode.analyze(xml, anchor)


if __name__ == "__main__":
    unittest.main()
