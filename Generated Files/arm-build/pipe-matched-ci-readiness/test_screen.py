import importlib.util
import json
import os
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from identity_map import exact_mapping
from screen import (
    HERE,
    SOURCE_REVISION,
    git,
    load,
    phase,
    prepare_source,
    schedule,
    source_snapshot,
    tiny_outcome,
)
from screen import (
    test_command as command_for_test,
)


class ScreenContracts(unittest.TestCase):
    def test_phase_timing_preserves_the_subprocess_audit_summary(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            summary = folder / "final-audit.json"

            def audit_command(*args, **kwargs):
                summary.write_text('{"status":"PASS_SELECTED_PAIR_ONLY"}')
                return SimpleNamespace(returncode=0)

            with patch("screen.subprocess.run", side_effect=audit_command):
                timing = phase(["audit"], folder, {}, folder, "final-audit", 1)
            self.assertEqual(load(summary)["status"], "PASS_SELECTED_PAIR_ONLY")
            self.assertEqual(load(folder / "final-audit-timing.json"), timing)

    def test_phase_reports_open_one_file_and_preserve_every_record(self):
        with (
            TemporaryDirectory() as temporary,
            patch.dict(
                os.environ,
                {
                    "CORRECTNESS_OUTPUT": temporary,
                    "CORRECTNESS_SOURCE": temporary,
                    "CHECK_COVERAGE": "0",
                },
            ),
        ):
            spec = importlib.util.spec_from_file_location(
                "buffered_observer_contract", HERE / "observer.py"
            )
            observer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(observer)
            with patch.object(
                Path, "cwd", side_effect=AssertionError("Unexpected cwd IO")
            ):
                fixture = observer.pytest_fixture_setup(
                    SimpleNamespace(argname="unrelated"), SimpleNamespace()
                )
                next(fixture)
                with self.assertRaises(StopIteration):
                    next(fixture)
            opened = []
            original_open = Path.open

            def counted_open(path, *args, **kwargs):
                opened.append(path)
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", counted_open):
                observer.pytest_sessionstart(None)
                for number in range(1000):
                    observer.pytest_runtest_logreport(
                        SimpleNamespace(
                            nodeid=f"test_{number}",
                            when="call",
                            outcome="passed",
                            duration=0.125,
                        )
                    )
                observer.pytest_sessionfinish(None, 0)
            output = Path(temporary) / "phases-controller.jsonl"
            self.assertEqual(opened, [output])
            records = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(
                [
                    {
                        key: value
                        for key, value in row.items()
                        if key in ("nodeid", "when", "outcome", "worker")
                    }
                    for row in records
                ],
                [
                    {
                        "nodeid": f"test_{number}",
                        "when": "call",
                        "outcome": "passed",
                        "worker": "controller",
                    }
                    for number in range(1000)
                ],
            )
            self.assertTrue(all(row["duration_seconds"] == 0.125 for row in records))
            self.assertTrue(all(row["completion_monotonic_ns"] > 0 for row in records))

    def test_git_overrides_inherited_newline_configuration(self):
        with patch(
            "screen.subprocess.run", return_value=SimpleNamespace(stdout=b"")
        ) as run:
            git(Path("source"), "apply", "owner.patch")
        self.assertEqual(
            run.call_args.args[0],
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "-C",
                "source",
                "apply",
                "owner.patch",
            ],
        )

    def test_source_patch_uses_the_same_controlled_git(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "tests").mkdir()
            (source / "tests" / "utils.py").write_bytes(b"fixture")
            with (
                patch(
                    "screen.git", side_effect=[SOURCE_REVISION.encode(), b"", b""]
                ) as run,
                patch("screen.corrected", return_value=b"corrected"),
            ):
                prepare_source(source)
            self.assertEqual(
                run.call_args.args,
                (source, "apply", str(HERE / "resource-owner.patch")),
            )

    def test_source_snapshot_rejects_and_names_changed_bytes(self):
        source = Path("owned-source")
        expected = load(HERE / "source-manifest.json")

        def changed_digest(path):
            name = path.relative_to(source).as_posix()
            return "0" * 64 if name == "fastapi/applications.py" else expected[name]

        with patch("screen.digest", side_effect=changed_digest):
            with self.assertRaisesRegex(AssertionError, r"fastapi/applications\.py"):
                source_snapshot(source)

    def test_schedule_excludes_two_warmups_then_one_screen_pair(self):
        self.assertEqual(schedule()[:2], [("serial", False), ("parallel", False)])
        self.assertEqual(
            schedule()[2:],
            [
                ("serial", True),
                ("parallel", True),
            ],
        )

    def test_command_only_worker_options_change(self):
        args = SimpleNamespace(output=Path("evidence"), workers=3)
        folder = Path("same-output")
        serial, parallel = [
            command_for_test(args, folder, arm) for arm in ("serial", "parallel")
        ]
        self.assertEqual(serial[:-1], parallel[:-3])
        self.assertEqual(
            parallel[-3:], ["3", "--dist=loadgroup", "--max-worker-restart=0"]
        )
        self.assertIn("tests", serial)
        self.assertNotIn("--cov-context", serial)
        self.assertNotIn("-rA", serial)

    def test_group_mapping_rejects_suffix_relabel(self):
        node = "tests/test_path.py::test_text_get"
        self.assertEqual(
            exact_mapping([node], [node + "@shared-main-app"], True),
            {node + "@shared-main-app": node},
        )
        with self.assertRaises(AssertionError):
            exact_mapping([node], [node + "@arbitrary"], True)

    def test_tiny_outcome_rejects_dropped_tests(self):
        tree = ET.ElementTree(
            ET.fromstring(
                '<testsuites><testsuite><testcase name="one"/></testsuite></testsuites>'
            )
        )
        with patch("screen.ET.parse", return_value=tree):
            with self.assertRaises(AssertionError):
                tiny_outcome(Path("unused"))


if __name__ == "__main__":
    unittest.main()
