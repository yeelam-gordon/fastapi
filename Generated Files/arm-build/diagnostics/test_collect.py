"""Focused stdlib tests; child platform doubles are unit fixtures, not proof."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

import collect

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "unit_arm_diag_hook", HERE / "hook" / "arm_diag_hook.py"
)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.root = HERE / ("test-owned-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.receipts = self.root / "receipts"
        self.upload = self.root / "upload"
        self.receipts.mkdir()
        self.upload.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def receipt(self, role, number=1, **changes):
        pid = str(number)
        (self.receipts / f"{pid}.start.tsv").write_text(
            f"run\tresource\t{role}\t{pid}\t99\t100\n", encoding="utf-8"
        )
        snapshot = {
            "cpu": {
                "status": "measured",
                "unit": "seconds",
                "scope": "self_all_threads",
                "user_seconds": 1.0,
                "kernel_seconds": 0.5,
            },
            "memory": {"rss": {"status": "measured", "value": 20, "unit": "bytes"}},
            "io": {"reads": {"status": "measured", "value": 2, "unit": "operations"}},
        }
        data = {
            "identity": "run",
            "mode": "resource",
            "role": role,
            "pid": number,
            "ppid": 99,
            "start_ns": 100,
            "end_ns": 200,
            "wall_seconds": 1e-7,
            "scope": "actual command",
            "bootstrap_end_ns": 90,
            "export_start_ns": 210,
            "status": "measured",
            "clock": "monotonic_ns",
            "performance_eligible": False,
            "snapshots": {"start": snapshot, "end": snapshot},
            "runtime": {"backend_version": "2.5.0"},
        }
        data.update(changes)
        collect.write_json(self.receipts / f"{pid}.end.json", data)

    def all_roles(self):
        for number, role in enumerate(sorted(collect.REQUIRED), 1):
            self.receipt(role, number)

    def ledger(self):
        return collect.coverage(self.receipts, "run", "resource", self.upload)

    def test_role_classification(self):
        for symbol, role in hook.ROLES.items():
            with self.subTest(symbol=symbol):
                self.assertEqual(hook.classify(f"backend.{symbol}({{}})"), role)
                self.assertEqual(hook.classify(f'getattr(backend, "{symbol}")()'), role)
        self.assertEqual(
            hook.classify("backend.prepare_metadata_for_build_wheel()"),
            "additional-unknown",
        )
        self.assertEqual(hook.classify("mybuild_wheelish()"), "additional-unknown")

    def test_complete_roles_and_additional_retained(self):
        self.all_roles()
        self.receipt("additional-unknown", 5)
        ledger = self.ledger()
        self.assertEqual(ledger["status"], "complete")
        self.assertEqual(len(ledger["children"]), 5)
        self.assertIsNone(ledger["family_cpu"]["value"])

    def test_missing_failed_stale_and_unfinished_receipts(self):
        self.all_roles()
        for mutation in (
            {"identity": "stale"},
            {"status": "failed"},
            {"end_ns": 90},
            {"clock": "wall"},
            {"performance_eligible": True},
        ):
            with self.subTest(mutation=mutation):
                self.receipt("build-sdist", 1, **mutation)
                self.assertEqual(self.ledger()["status"], "failed")
        (self.receipts / "1.end.json").unlink()
        self.assertEqual(self.ledger()["status"], "failed")
        self.assertTrue(self.ledger()["missing_required_roles"])

    def test_orphan_end_is_not_coverage(self):
        collect.write_json(self.receipts / "33.end.json", {})
        self.assertEqual(self.ledger()["orphan_end_receipts"], ["33.end.json"])
        self.assertEqual(self.ledger()["status"], "failed")

    def test_clock_scope_and_missing_metrics_are_not_zero(self):
        start = {
            "cpu": {
                "status": "measured",
                "scope": "self_all_threads",
                "unit": "seconds",
                "user_seconds": 2.0,
                "kernel_seconds": 1.0,
            }
        }
        end = {"cpu": dict(start["cpu"], user_seconds=3.0, kernel_seconds=1.5)}
        delta = collect.cpu_delta(start, end)
        self.assertEqual(delta["user_seconds"]["value"], 1.0)
        self.assertEqual(delta["kernel_seconds"]["value"], 0.5)
        end["cpu"]["scope"] = "tree"
        self.assertIsNone(collect.cpu_delta(start, end)["user_seconds"]["value"])
        self.assertIsNone(collect.cpu_delta({}, {})["kernel_seconds"]["value"])
        self.assertEqual(
            collect.counter_status({"rss": {"status": "unavailable", "value": None}}),
            "unavailable",
        )

    def test_missing_platform_is_partial_not_success(self):
        self.all_roles()
        self.receipt(
            "build-sdist",
            1,
            snapshots={"start": {}, "end": {}},
            errors=["platform:ImportError"],
        )
        self.assertEqual(self.ledger()["status"], "partial")

    def test_privacy_redaction_and_environment(self):
        text = 'Authorization: Bearer abcd https://user:pw@example.org/?token=xyz password=hunter2 ghp_123abc C:\\Users\\person --token cli-secret {"token": "json-secret"}'
        redacted = collect.redact(text, [("C:\\Users\\person", "<home>")])
        for secret in (
            "abcd",
            "user:pw",
            "xyz",
            "hunter2",
            "ghp_123abc",
            "C:\\Users\\person",
            "cli-secret",
            "json-secret",
        ):
            self.assertNotIn(secret, redacted)
        env = collect.build_environment(
            {
                "PATH": "system",
                "PYTHONPATH": "controller-packages",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPROFILEIMPORTTIME": "1",
                "UV_BUILD_BACKEND": "custom",
                "ARM_DIAG_PASS": "old",
            },
            self.root / "cache",
            self.root / "tmp",
        )
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONDONTWRITEBYTECODE", env)
        self.assertNotIn("PYTHONPROFILEIMPORTTIME", env)
        self.assertNotIn("ARM_DIAG_PASS", env)
        self.assertNotIn("UV_BUILD_BACKEND", env)
        self.assertEqual(env["UV_OFFLINE"], "1")

    def test_invalid_profiles_are_not_presence_proof(self):
        bad = self.receipts / "bad.pstats"
        bad.write_bytes(b"not a profile")
        with self.assertRaises((ValueError, EOFError, TypeError)):
            collect.profile_export(bad, ())

    def test_stock_uv_output_marker_is_not_an_artifact(self):
        (self.root / "package.whl").write_bytes(b"wheel")
        (self.root / "package.tar.gz").write_bytes(b"sdist")
        # Use a separate output directory from the test's receipt/upload dirs.
        output = self.root / "out"
        output.mkdir()
        for name in ("package.whl", "package.tar.gz"):
            shutil.move(self.root / name, output / name)
        (output / ".gitignore").write_bytes(b"*")
        collect.verify_artifact_membership(output)
        (output / ".gitignore").write_bytes(b"unexpected content")
        with self.assertRaisesRegex(ValueError, "artifact membership"):
            collect.verify_artifact_membership(output)

    def test_setup_failure_preserves_private_upload_boundary(self):
        destination = self.root / "failed-run"
        result = collect.main(
            [
                "--uv",
                str(self.root / "missing-uv.exe"),
                "--source-checkout",
                str(self.root),
                "--wheelhouse",
                str(self.root / "missing-wheelhouse"),
                "--output",
                str(destination),
            ]
        )
        self.assertEqual(result, 1)
        report = json.loads((destination / "upload" / "report.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["performance_eligible"])
        self.assertTrue((destination / "private_raw").is_dir())
        self.assertEqual(
            {path.name for path in (destination / "upload").iterdir()},
            {"report.json"},
        )
        self.assertNotIn("PATH", report)

    @unittest.skipUnless(hasattr(sys, "monitoring"), "CPython monitoring required")
    def test_separate_profilers_on_actual_command_frame(self):
        injected = self.root / "hook"
        shutil.copytree(
            HERE / "hook", injected, ignore=shutil.ignore_patterns("__pycache__")
        )
        (injected / "arm_diag_platform.py").write_text(
            "def process_snapshot(): return {'status': 'unavailable'}\n",
            encoding="utf-8",
        )
        # A labelled unit backend verifies hook machinery, not stock uv coverage.
        package = injected / "pdm"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "backend.py").write_text(
            "def build_wheel(): return bytearray(4096)\n", encoding="utf-8"
        )
        for mode in ("cprofile", "importtime", "memory"):
            with self.subTest(mode=mode):
                receipts = self.root / mode
                receipts.mkdir()
                env = dict(
                    os.environ,
                    PYTHONPATH=str(injected),
                    ARM_DIAG_PASS=mode,
                    ARM_DIAG_RECEIPTS=str(receipts),
                    ARM_DIAG_ID="unit",
                )
                if mode == "importtime":
                    env["PYTHONPROFILEIMPORTTIME"] = "1"
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "import pdm.backend; result=pdm.backend.build_wheel()",
                    ],
                    env=env,
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                ends = list(receipts.glob("*.end.json"))
                self.assertEqual(len(ends), 1, result.stderr)
                end = json.loads(ends[0].read_text())
                self.assertEqual(end["role"], "build-wheel")
                if mode == "cprofile":
                    exported = collect.profile_export(
                        receipts / f"{end['pid']}.pstats", (), "build-wheel"
                    )
                    self.assertTrue(exported["full_stats"])
                    self.assertTrue(
                        any(row["callers"] for row in exported["full_stats"])
                    )
                elif mode == "importtime":
                    log = (receipts / f"{end['pid']}.imports.raw.log").read_text()
                    self.assertIn("pdm.backend", log)
                else:
                    self.assertGreater(end["allocation"]["peak"], 0)
                    self.assertTrue(end["allocation"]["end_live_top"])

    @unittest.skipUnless(hasattr(sys, "monitoring"), "CPython monitoring required")
    def test_real_command_monitoring_success_failure_and_import_child(self):
        injected = self.root / "hook"
        shutil.copytree(
            HERE / "hook", injected, ignore=shutil.ignore_patterns("__pycache__")
        )
        # Unit-only stub, never used by the production collector.
        (injected / "arm_diag_platform.py").write_text(
            "def process_snapshot():\n"
            "    return {'cpu': {'status':'unavailable', 'reason':'unit fixture'}}\n",
            encoding="utf-8",
        )
        for index, (command, succeeds) in enumerate(
            (
                ("def build_sdist(): pass\nbuild_sdist()", True),
                (
                    "def build_wheel(): raise ValueError('unit failure')\nbuild_wheel()",
                    False,
                ),
            )
        ):
            receipts = self.root / str(index)
            receipts.mkdir()
            env = dict(
                os.environ,
                PYTHONPATH=str(injected),
                ARM_DIAG_PASS="resource",
                ARM_DIAG_RECEIPTS=str(receipts),
                ARM_DIAG_ID="unit",
            )
            result = subprocess.run(
                [sys.executable, "-c", command],
                env=env,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode == 0, succeeds, result.stderr)
            ends = list(receipts.glob("*.end.json"))
            self.assertEqual(len(ends), 1, result.stderr)
            end = json.loads(ends[0].read_text())
            self.assertEqual(end["status"], "measured" if succeeds else "failed")
            self.assertGreater(end["end_ns"], end["start_ns"])
            self.assertEqual(end["role"], "build-sdist" if succeeds else "build-wheel")
            self.assertNotIn("generated_command", end)
            self.assertFalse(end["ignore_environment"])
            self.assertLessEqual(end["bootstrap_end_ns"], end["start_ns"])
            self.assertGreaterEqual(end["export_start_ns"], end["end_ns"])


if __name__ == "__main__":
    unittest.main()
