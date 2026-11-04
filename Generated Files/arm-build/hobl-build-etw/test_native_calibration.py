import copy
import io
import json
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import capture
import native_calibration as calibration
from test_typed_events import row


class NativeCalibration(unittest.TestCase):
    def setUp(self):
        self.folder = Path(__file__).parent / ("test-private-" + uuid.uuid4().hex)
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = self.folder / "dto.jsonl"
        self.anchor = {
            "pid": 10,
            "qpc_before": 99,
            "qpc_after": 101,
            "qpc_end": 601,
            "creation_filetime": 1000,
            "filetime_after": 1000,
            "qpc_frequency": 1000,
        }
        self.handshake = {
            "schema": 1,
            "pid": 10,
            "tid": 12,
            "qpc_frequency": 1000,
            "thread_qpc_before": 110,
            "creation_filetime": 1000,
            "filetime_after": 301000,
            "before_wait": 150,
            "released": 300,
            "after_wait": 310,
            "work_end": 350,
        }
        self.records = [
            row("processStart", 100, payload={"parentPid": 1}),
            row("threadStart", 120, tid=12),
            self.switch(125, 99, 12, 1),
            self.switch(160, 12, 99, 5),
            dict(
                row("readyThread", 302, tid=999, version=2, opcode=50),
                sourceType="DispatcherReadyThreadTraceData",
                payload={
                    "awakenedTid": 12,
                    "flags": 0,
                    "adjustReason": 0,
                    "adjustIncrement": 0,
                    "processorNumber": 0,
                },
            ),
            self.switch(305, 99, 12, 1),
            self.switch(340, 12, 99, 5),
            row("threadStop", 360, tid=12, opcode=2),
            row("processStop", 600, payload={"parentPid": 1}, opcode=2),
            row(
                "header",
                90,
                None,
                None,
                {
                    "perfFreq": 1000,
                    "reservedFlags": 1,
                    "eventsLost": 0,
                    "buffersLost": 0,
                    "sessionStartFileTime": 1,
                    "sessionEndFileTime": 10000001,
                    "lastQpc": 602,
                },
            ),
        ]
        self.records = [dict(record, schema=2) for record in self.records]

    def switch(self, qpc, old, new, state):
        return dict(
            row("cswitch", qpc, tid=999, version=5, opcode=36),
            sourceType="CSwitchTraceData",
            payload={
                "oldTid": old,
                "newTid": new,
                "oldThreadState": state,
                "oldThreadWaitReason": 6,
                "oldThreadWaitMode": 1,
                "processorNumber": 0,
            },
        )

    def qualify(self, records=None):
        self.path.write_text(
            "".join(
                json.dumps(record) + "\n"
                for record in (self.records if records is None else records)
            ),
            encoding="utf-8",
        )
        return calibration.qualify(self.path, self.anchor, self.handshake)

    def test_payload_target_and_public_allowlist(self):
        summary = self.qualify()
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["controlled_waiting_ticks"], 140)
        self.assertGreater(summary["unknown_ticks"], 0)
        self.assertEqual(set(summary), calibration.PUBLIC_KEYS)
        with self.assertRaisesRegex(ValueError, "public_schema"):
            calibration.validate_public(dict(summary, tid=12))
        records = copy.deepcopy(self.records)
        records[4]["tid"] = 12
        records[4]["payload"]["awakenedTid"] = 999
        self.assertEqual(self.qualify(records)["status"], "UNQUALIFIED")

    def test_markers_do_not_prove_wait_or_release_identity(self):
        records = copy.deepcopy(self.records)
        records[3]["payload"]["oldThreadState"] = 1
        self.assertEqual(self.qualify(records)["reason"], "insufficient_wait")
        records = copy.deepcopy(self.records)
        records[4]["qpc"] = 290
        self.assertEqual(self.qualify(records)["reason"], "insufficient_wait")

    def test_loss_censor_and_missing_switch_boundary(self):
        records = copy.deepcopy(self.records)
        records[-1]["payload"]["eventsLost"] = 1
        self.assertEqual(self.qualify(records)["reason"], "trace_loss")
        records = [record for record in self.records if record["kind"] != "threadStop"]
        self.assertEqual(self.qualify(records)["reason"], "missing_target_lifetime")
        records = [record for record in self.records if record["kind"] != "processStop"]
        self.assertEqual(self.qualify(records)["reason"], "incomplete_trace")
        records = [record for record in self.records if record["qpc"] != 340]
        self.assertEqual(self.qualify(records)["reason"], "missing_state_boundaries")
        records = [record for record in records if record["qpc"] != 160]
        self.assertEqual(self.qualify(records)["status"], "UNQUALIFIED")

    def test_conflicting_native_owner_frequency_and_schema_are_errors(self):
        for field, value, reason in (
            ("pid", 999, "owner_mismatch"),
            ("qpc_frequency", 999, "frequency_mismatch"),
            ("creation_filetime", 100000000, "native_creation_mismatch"),
            ("thread_qpc_before", 130, "thread_birth"),
        ):
            original = self.handshake[field]
            self.handshake[field] = value
            with self.assertRaisesRegex(ValueError, reason):
                self.qualify()
            self.handshake[field] = original
        records = copy.deepcopy(self.records)
        records[1]["processBirthQpc"] = 99
        with self.assertRaisesRegex(ValueError, "owner_mismatch"):
            self.qualify(records)
        records[1]["schema"] = 1
        with self.assertRaisesRegex(ValueError, "requires_schema2"):
            self.qualify(records)

    def test_header_clock_completeness_and_conflicts(self):
        records = copy.deepcopy(self.records)
        records[-1]["payload"]["reservedFlags"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported_clock"):
            self.qualify(records)
        records = copy.deepcopy(self.records)
        records[-1]["payload"]["lastQpc"] = 602
        records[-1]["payload"]["sessionEndFileTime"] = 0
        self.assertEqual(self.qualify(records)["reason"], "incomplete_trace")
        with self.assertRaisesRegex(ValueError, "calibration_header"):
            self.qualify(self.records + [self.records[-1]])
        with self.assertRaisesRegex(ValueError, "thread_conflict"):
            self.qualify(self.records[:2] + [self.records[1]] + self.records[2:])
        records = copy.deepcopy(self.records)
        records[4]["payload"]["awakenedTid"] = None
        with self.assertRaisesRegex(ValueError, "schema"):
            self.qualify(records)

    def test_controller_default_off_and_failed_gate_stops_before_warmup(self):
        controller = capture.Controller(
            self.folder, self.folder, self.folder, Path("uv")
        )
        with patch.object(controller, "trace") as trace:
            controller.calibration(
                Path("python"), {"HOBL_PRIVATE_WAIT_CALIBRATION": "1"}
            )
            self.assertNotIn("HOBL_PRIVATE_WAIT_CALIBRATION", trace.call_args.args[2])
            self.assertFalse(controller.wait_calibration)
        controller.wait_calibration = True
        self.qualify()
        (self.folder / "wait-handshake.json").write_text(json.dumps(self.handshake))
        with patch.object(controller, "trace") as trace:
            controller.calibration(Path("python"), {})
            self.assertEqual(
                trace.call_args.args[2]["HOBL_PRIVATE_WAIT_CALIBRATION"], "1"
            )
        controller.qualify_wait(self.folder, self.path, self.anchor)
        self.qualify(
            [record for record in self.records if record["kind"] != "threadStop"]
        )
        with patch.object(controller, "command") as command:
            with self.assertRaises(capture.Failure) as failure:
                controller.qualify_wait(self.folder, self.path, self.anchor)
            self.assertEqual(failure.exception.reason, "native_calibration")
            command.assert_not_called()
        summary = json.loads((self.folder / "calibration-wait.json").read_text())
        self.assertEqual(summary["status"], "UNQUALIFIED")

    def test_fake_run_failed_calibration_never_reaches_build(self):
        controller = capture.Controller(
            self.folder,
            self.folder,
            self.folder,
            Path("uv"),
            wait_calibration=True,
            calibration_only=True,
        )
        self.qualify(
            [record for record in self.records if record["kind"] != "threadStop"]
        )
        with self.fake_controller(controller) as (stages, traces, cleanup):
            with self.assertRaises(capture.Failure):
                controller.run()
            cleanup.assert_not_called()
        self.assertNotIn("warmup", stages)
        self.assertEqual(stages, ["preflight"])
        self.assertFalse((self.folder / "prepared").exists())
        self.assertEqual(traces, ["calibration"])

    @contextmanager
    def fake_controller(self, controller):
        controller.wpr = __file__
        (self.folder / "wait-handshake.json").write_text(json.dumps(self.handshake))
        (self.folder / "0.stdout").write_text("not recording")
        observed_stages = []
        observed_traces = []

        def fake_command(*args, **kwargs):
            observed_stages.append(controller.stage)

        def fake_trace(phase, command, env):
            observed_traces.append(phase)
            if controller.calibration_only:
                self.assertEqual(command[0], sys.executable)
                self.assertFalse(
                    any(
                        key.startswith(
                            (
                                "PYTHON",
                                "PIP_",
                                "UV_",
                                "PYTEST_",
                                "COVERAGE_",
                                "COV_CORE_",
                            )
                        )
                        for key in env
                    )
                )
            if phase == "calibration" and controller.wait_calibration:
                self.assertEqual(env["HOBL_PRIVATE_WAIT_CALIBRATION"], "1")
                controller.qualify_wait(self.folder, self.path, self.anchor)

        with (
            patch.object(capture, "hosted_gate"),
            patch.object(
                capture.ctypes.windll.shell32, "IsUserAnAdmin", return_value=True
            ),
            patch.object(
                capture.shutil,
                "disk_usage",
                return_value=SimpleNamespace(free=9 * 1024**3),
            ),
            patch.object(controller, "prepare_reader"),
            patch.object(controller, "recorder_inventory"),
            patch.object(controller, "validate_calibration_python"),
            patch.object(controller, "command", side_effect=fake_command),
            patch.object(controller, "trace", side_effect=fake_trace),
            patch.object(controller, "cleanup", wraps=controller.cleanup) as cleanup,
            patch.object(controller, "check_artifacts"),
            patch.object(capture.shutil, "move"),
        ):
            yield observed_stages, observed_traces, cleanup

    def test_fake_run_default_still_warms_and_builds(self):
        controller = capture.Controller(
            self.folder, self.folder, self.folder, Path("uv")
        )
        with self.fake_controller(controller) as (stages, traces, cleanup):
            controller.run()
            cleanup.assert_not_called()
        self.assertFalse(controller.wait_calibration)
        self.assertFalse(controller.calibration_only)
        self.assertIn("warmup", stages)
        self.assertEqual(traces, ["calibration", "build"])

    def test_fake_run_only_mode_cleans_up_without_warmup_or_build(self):
        self.qualify()
        controller = capture.Controller(
            self.folder,
            self.folder,
            self.folder,
            Path("uv"),
            wait_calibration=True,
            calibration_only=True,
        )
        with self.fake_controller(controller) as (stages, traces, cleanup):
            controller.run()
            cleanup.assert_called_once_with()
        self.assertEqual(controller.stage, "complete")
        self.assertEqual(stages, ["preflight"])
        self.assertEqual(traces, ["calibration"])
        self.assertFalse((self.folder / "prepared").exists())
        self.assertEqual(
            json.loads((self.folder / "calibration-wait.json").read_text())["status"],
            "PASS",
        )

    def test_cli_defaults_forwarding_and_invalid_only_combination(self):
        arguments = [
            "--private",
            str(self.folder),
            "--public",
            str(self.folder),
            "--source",
            str(self.folder),
            "--uv",
            str(self.folder / "uv"),
        ]
        parsed = capture.parse_args(arguments)
        self.assertFalse(parsed.wait_calibration)
        self.assertFalse(parsed.calibration_only)
        with patch.object(capture, "Controller") as controller:
            self.assertEqual(
                capture.main(arguments + ["--wait-calibration", "--calibration-only"]),
                0,
            )
            self.assertEqual(
                controller.call_args.kwargs,
                {"wait_calibration": True, "calibration_only": True},
            )
            controller.return_value.run.assert_called_once_with()
        with (
            patch.object(capture, "Controller") as controller,
            redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as failure:
                capture.main(arguments + ["--calibration-only"])
            self.assertEqual(failure.exception.code, 2)
            controller.assert_not_called()
        with self.assertRaisesRegex(ValueError, "requires_wait_calibration"):
            capture.Controller(
                self.folder, self.folder, self.folder, Path("uv"), calibration_only=True
            )

    def test_closing_switch_after_work_marker_can_bracket_residency(self):
        records = copy.deepcopy(self.records)
        records[6]["qpc"] = 355
        self.assertEqual(self.qualify(records)["status"], "PASS")

    def test_only_mode_native_python_checks_version_gil_and_machine(self):
        controller = capture.Controller(
            self.folder, self.folder, self.folder, Path("uv")
        )
        architecture = 0xAA64

        def machine(handle, process, native):
            process._obj.value = 0
            native._obj.value = architecture
            return 1

        with (
            patch.object(capture.sys, "version_info", (3, 13, 15)),
            patch.object(capture.sys, "_is_gil_enabled", return_value=True),
            patch.object(capture.sysconfig, "get_config_var", return_value=0),
            patch.object(
                capture.ctypes.windll.kernel32, "IsWow64Process2", side_effect=machine
            ),
        ):
            controller.validate_calibration_python()
            architecture = 0x8664
            with self.assertRaises(capture.Failure):
                controller.validate_calibration_python()
            with patch.object(capture.sys, "version_info", (3, 13, 14)):
                with self.assertRaises(capture.Failure):
                    controller.validate_calibration_python()
            with patch.object(capture.sys, "_is_gil_enabled", return_value=False):
                with self.assertRaises(capture.Failure):
                    controller.validate_calibration_python()


    def test_failure_reasons_never_export_exception_values(self):
        self.assertEqual(
            calibration.failure_reason(ValueError("ambiguous_same_qpc_subject")),
            "native_wait_subject_tie",
        )
        self.assertIn("native_wait_subject_tie", capture.REASONS)
        self.assertEqual(
            calibration.failure_reason(ValueError("ambiguous_owned_self_switch")),
            "native_wait_owned_self_switch",
        )
        self.assertIn("native_wait_owned_self_switch", capture.REASONS)
        for error in (
            ValueError(r"C:\private\subject-123.json"),
            ValueError(["private", 123]),
            KeyError("private-target"),
        ):
            self.assertEqual(calibration.failure_reason(error), "native_calibration")


if __name__ == "__main__":
    unittest.main()
