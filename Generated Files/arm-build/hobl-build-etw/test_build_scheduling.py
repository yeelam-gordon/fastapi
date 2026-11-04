import copy
import io
import json
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import build_scheduling
import capture
import observed_threads
import test_native_calibration
from test_typed_events import row


class BuildScheduling(unittest.TestCase):
    def setUp(self):
        self.fixture = test_native_calibration.NativeCalibration()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.proof = self.fixture.qualify()
        self.records = copy.deepcopy(self.fixture.records)

    def qualify(self, records=None, proof=None):
        self.fixture.path.write_text(
            "".join(
                json.dumps(record) + "\n"
                for record in (self.records if records is None else records)
            ),
            encoding="utf-8",
        )
        return build_scheduling.qualify(
            self.fixture.path,
            self.fixture.anchor,
            self.proof if proof is None else proof,
        )

    def test_partition_conserves_clipped_window_and_public_allowlist(self):
        public, private = self.qualify()
        self.assertEqual(public["status"], "AUXILIARY")
        self.assertEqual(public["window_ticks"], 500)
        self.assertEqual(public["threads"][0]["window_ticks"], 240)
        self.assertEqual(
            sum(
                public["threads"][0][state]
                for state in ("UNKNOWN", "WAITING", "RUNNABLE", "SCHEDULED")
            ),
            240,
        )
        self.assertEqual(private["partition"]["threads"][0]["lifetime"]["tid"], 12)
        self.assertEqual(set(public), build_scheduling.KEYS)
        with self.assertRaises(ValueError):
            build_scheduling.validate_public(
                {
                    key: value
                    for key, value in public.items()
                    if key != "known_scheduled_union_ticks"
                }
            )
        with self.assertRaises(ValueError):
            build_scheduling.validate_public(dict(public, pid=10))
        with self.assertRaises(ValueError):
            build_scheduling.validate_public(
                dict(public, threads=[dict(public["threads"][0], tid=12)])
            )
        self.assertNotIn("pid", json.dumps(public).lower())
        self.assertNotIn("qpc", json.dumps(public).lower())

    def test_child_union_clipping_and_earliest_tie(self):
        root = {"start": 100, "end": 600}
        self.assertEqual(
            build_scheduling.largest_window(
                root,
                [
                    {"start": 50, "end": 200},
                    {"start": 180, "end": 300},
                    {"start": 400, "end": 500},
                    {"start": 580, "end": 700},
                ],
            ),
            (300, 400),
        )
        self.assertIsNone(
            build_scheduling.largest_window(root, [{"start": 50, "end": 700}])
        )
        children = [
            dict(row("processStart", 200, pid=20, payload={"parentPid": 10}), schema=2),
            dict(row("processStart", 250, pid=30, payload={"parentPid": 20}), schema=2),
            dict(
                row("processStop", 450, pid=20, payload={"parentPid": 10}, opcode=2),
                schema=2,
            ),
            dict(
                row("processStop", 550, pid=30, payload={"parentPid": 20}, opcode=2),
                schema=2,
            ),
        ]
        public, _ = self.qualify(
            sorted(self.records + children, key=lambda record: record["qpc"])
        )
        self.assertEqual(
            (public["window_offset_ticks"], public["window_ticks"]), (350, 150)
        )
        self.assertEqual(public["status"], "UNQUALIFIED")

    def test_explicit_lifetimes_reuse_and_censor_counts(self):
        root = {"pid": 10, "start": 100, "end": 600}
        records = [
            dict(row("threadStart", 110, tid=12), schema=2),
            dict(row("threadStop", 150, tid=12, opcode=2), schema=2),
            dict(row("threadStart", 160, tid=12), schema=2),
            dict(row("threadStop", 180, tid=12, opcode=2), schema=2),
            dict(row("threadDCStart", 190, tid=13, opcode=3), schema=2),
            dict(row("threadStop", 200, tid=13, opcode=2), schema=2),
            dict(row("threadStart", 210, tid=14), schema=2),
            dict(row("threadStart", 590, tid=15), schema=2),
            dict(row("threadStop", 610, tid=15, opcode=2), schema=2),
        ]
        lives, counts = observed_threads.collect(records, root, "process-index-0")
        self.assertEqual(
            [(life["start"], life["end"]) for life in lives], [(110, 150), (160, 180)]
        )
        self.assertEqual(counts, {"unclosed": 1, "unresolved": 2, "censored": 1})
        public, _ = self.qualify(
            [record for record in self.records if record["kind"] != "threadStop"]
        )
        self.assertEqual(public["reason"], "no_complete_root_threads")
        self.assertEqual(public["coverage"]["unclosed"], 1)

    def test_model_keeps_reused_tid_lifetimes_separate(self):
        extra = [
            dict(row("threadStart", 400, tid=12), schema=2),
            dict(row("threadStop", 500, tid=12, opcode=2), schema=2),
        ]
        public, private = self.qualify(
            sorted(self.records + extra, key=lambda record: record["qpc"])
        )
        self.assertEqual(
            [thread["window_ticks"] for thread in public["threads"]], [240, 100]
        )
        self.assertEqual(
            [thread["lifetime"]["start"] for thread in private["partition"]["threads"]],
            [120, 400],
        )

    def test_overlapping_threads_remain_rows_not_summed_process_time(self):
        self.records = [
            record for record in self.records if record["qpc"] not in (302, 305, 340)
        ]
        self.records[2]["qpc"] = 130
        extra = [
            dict(row("threadStart", 121, tid=13), schema=2),
            dict(self.fixture.switch(140, 98, 13, 1), schema=2),
            dict(self.fixture.switch(170, 13, 98, 5), schema=2),
            dict(row("threadStop", 360, tid=13, opcode=2), schema=2),
        ]
        for record in extra[1:3]:
            record["payload"]["processorNumber"] = 1
        public, _ = self.qualify(
            sorted(self.records + extra, key=lambda record: record["qpc"])
        )
        self.assertEqual(
            [thread["SCHEDULED"] for thread in public["threads"]], [30, 30]
        )
        self.assertEqual(public["known_scheduled_union_ticks"], 40)
        for invalid in (29, 61, public["window_ticks"] + 1):
            with self.assertRaises(ValueError):
                build_scheduling.validate_public(
                    dict(public, known_scheduled_union_ticks=invalid)
                )
        self.assertNotIn("scheduled_ticks", public)

    def test_exact_failure_tags_and_private_unknown_causes(self):
        folder = self.fixture.folder
        controller = capture.Controller(folder, folder, folder, Path("uv"))
        controller.native_wait_proof = self.proof
        for error, expected in (
            (ValueError("calibration_source"), "build_scheduling_source"),
            (ValueError("unsupported_clock"), "build_scheduling_clock"),
            (ValueError("calibration_owner_mismatch"), "build_scheduling_owner"),
            (ValueError("ambiguous_same_processor_qpc"), "build_scheduling_cpu_tie"),
            (ValueError("private-pid-123-path"), "build_scheduling_invalid"),
            (ValueError(["private-unhashable"]), "build_scheduling_invalid"),
            (ValueError({"private": 123}), "build_scheduling_invalid"),
            (KeyError("private-key"), "build_scheduling_invalid"),
        ):
            with patch.object(build_scheduling, "qualify", side_effect=error):
                with self.assertRaises(capture.Failure) as failure:
                    controller.qualify_build_scheduling(
                        folder, self.fixture.path, self.fixture.anchor
                    )
            self.assertEqual(failure.exception.reason, expected)
            self.assertEqual(capture.safe_reason(failure.exception), expected)
            self.assertIs(failure.exception.__cause__, error)
            self.assertIn(expected, capture.REASONS)
        self.assertFalse((folder / "build-scheduling.json").exists())

    def test_calibration_does_not_authorize_invalid_root_input(self):
        with self.assertRaises(ValueError):
            self.qualify(
                proof=dict(self.proof, status="UNQUALIFIED", reason="trace_loss")
            )
        records = copy.deepcopy(self.records)
        records[1]["processBirthQpc"] = 99
        with self.assertRaisesRegex(ValueError, "owner_mismatch"):
            self.qualify(records)
        records = copy.deepcopy(self.records)
        records[1]["opcode"] = 3
        with self.assertRaisesRegex(ValueError, "source"):
            self.qualify(records)
        records = copy.deepcopy(self.records)
        records[-1]["payload"]["lastQpc"] = 599
        with self.assertRaisesRegex(ValueError, "clock_conflict"):
            self.qualify(records)
        public, _ = self.qualify(
            [record for record in self.records if record["kind"] != "processStop"]
        )
        self.assertEqual(public["reason"], "incomplete_trace")

    def test_cli_and_controller_gate_and_future_build(self):
        folder = self.fixture.folder
        arguments = [
            "--private",
            str(folder),
            "--public",
            str(folder),
            "--source",
            str(folder),
            "--uv",
            str(folder / "uv"),
        ]
        self.assertFalse(capture.parse_args(arguments).build_scheduling)
        for flags in (
            ["--build-scheduling"],
            ["--wait-calibration", "--calibration-only", "--build-scheduling"],
        ):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                capture.parse_args(arguments + flags)
        with self.assertRaises(ValueError):
            capture.Controller(
                folder, folder, folder, Path("uv"), build_scheduling=True
            )
        controller = capture.Controller(
            folder,
            folder,
            folder,
            Path("uv"),
            wait_calibration=True,
            build_scheduling=True,
        )
        with self.assertRaises(capture.Failure) as failure:
            controller.qualify_build_scheduling(
                folder, self.fixture.path, self.fixture.anchor
            )
        self.assertEqual(failure.exception.reason, "build_scheduling_native_proof")
        self.assertFalse((folder / "build-scheduling.json").exists())
        with self.fixture.fake_controller(controller) as (stages, traces, _):
            controller.run()
        self.assertIn("warmup", stages)
        self.assertEqual(traces, ["calibration", "build"])
        self.qualify()
        controller.qualify_build_scheduling(
            folder, self.fixture.path, self.fixture.anchor
        )
        self.assertEqual(
            json.loads((folder / "build-scheduling.json").read_text())["status"],
            "AUXILIARY",
        )

    def test_future_build_requires_actual_same_controller_pass(self):
        folder = self.fixture.folder
        controller = capture.Controller(
            folder,
            folder,
            folder,
            Path("uv"),
            wait_calibration=True,
            build_scheduling=True,
        )
        with (
            self.fixture.fake_controller(controller),
            patch.object(controller, "qualify_wait"),
        ):
            with self.assertRaises(capture.Failure):
                controller.run()
