"""Q-only SELF audit and instrumentation-boundary regressions."""

import json
import os
from unittest.mock import patch

import cpu_audit
import driver
from guards import environment
from source import save
from test_cpu_hook import hook
from test_reference import Fixture


class CpuAuditTests(Fixture):
    def fixtures(self, name, *, direct=False, missing=False):
        receipts, shards = self.root / (name + "-cpu"), self.root / (name + "-shards")
        receipts.mkdir()
        shards.mkdir()
        main = hook.cpu_record(
            101,
            55 if direct else 201,
            ["python", "-m", "coverage", "run", "-m", "pytest", "tests"],
            2.0,
            0.5,
        )
        cli = hook.cpu_record(
            102,
            101 if direct else 202,
            [
                "python",
                "-m",
                "coverage",
                "run",
                "-m",
                "fastapi",
                "dev",
                "non_existent_file.py",
            ],
            0.25,
            0.125,
        )
        save(receipts / "python-101.json", main)
        if not missing:
            save(receipts / "python-102.json", cli)
        for pid in (101, 102):
            (shards / f".coverage.host.pid{pid}.X.suffix").write_bytes(b"fixture")
        return receipts, shards, 101 if direct else 201

    def test_windows_redirector_and_direct_macos_entry_both_reconcile(self):
        for direct in (False, True):
            receipts, shards, entry = self.fixtures(str(direct), direct=direct)
            result = cpu_audit.audit(receipts, shards, entry, b"")
            self.assertTrue(result["covered_worker_receipts_complete"])
            self.assertEqual(result["observed_Python_self_user_seconds"], 2.25)
            self.assertEqual(result["observed_Python_self_system_seconds"], 0.625)
            self.assertFalse(result["performance_eligible"])

    def test_missing_counter_receipt_is_unknown_not_zero(self):
        receipts, shards, entry = self.fixtures("missing", missing=True)
        result = cpu_audit.audit(receipts, shards, entry, b"")
        self.assertFalse(result["covered_worker_receipts_complete"])
        self.assertEqual(result["missing_covered_pid_receipts"], [102])
        self.assertIsNone(result["observed_Python_self_total_seconds"])

    def test_invalid_counter_and_atexit_error_fail_closed(self):
        receipts, shards, entry = self.fixtures("bad")
        result = cpu_audit.audit(
            receipts, shards, entry, b"Exception ignored in atexit callback"
        )
        self.assertFalse(result["covered_worker_receipts_complete"])
        path = receipts / "python-102.json"
        row = json.loads(path.read_bytes())
        row["user_seconds"] = None
        save(path, row)
        result = cpu_audit.audit(receipts, shards, entry, b"")
        self.assertTrue(result["invalid_records"])
        self.assertIsNone(result["observed_Python_self_user_seconds"])

    def test_zero_counter_no_test_smoke_is_valid(self):
        receipts = self.root / "smoke"
        receipts.mkdir()
        save(
            receipts / "python-101.json",
            hook.cpu_record(101, 55, ["python", "-c", "pass"], 0, 0),
        )
        result = cpu_audit.smoke(receipts, 101, b"")
        self.assertTrue(result["complete"])
        self.assertEqual(
            result["valid_observed_Python_processes"][0]["self_cpu_seconds"], 0
        )

    def test_performance_paths_forbid_hook_even_when_cpu_flag_is_requested(self):
        run = driver.Run(self.root)
        for extra in (
            {"HOBL_CPU_RECEIPT_DIR": ""},
            {"HOBL_CPU_OTHER": "1"},
            {"PYTHONPATH": str(cpu_audit.HOOK)},
        ):
            with (
                self.subTest(extra=extra),
                patch.object(driver.subprocess, "run") as invoke,
            ):
                with self.assertRaises(RuntimeError):
                    run.command("trial", ["mock"], env={**run.env, **extra}, timed=True)
                invoke.assert_not_called()
        with patch.object(driver.subprocess, "Popen") as invoke:
            with self.assertRaises(RuntimeError):
                run.command("full-correctness", ["mock"], timed=True, cpu_receipt=True)
            invoke.assert_not_called()
        env = environment(self.root / "synthetic", {"HOBL_CPU_RECEIPT_DIR": "private"})
        self.assertNotIn("HOBL_CPU_RECEIPT_DIR", env)

    def test_existing_startup_hook_is_not_shadowed(self):
        run = driver.Run(self.root)
        run.test_python, run.source = self.root / "python", self.root
        run.full_env = {"PYTHONPATH": "docs_src"}
        guard = {"existing_hooks": ["sitecustomize"], "trace": False, "profile": False}
        with patch.object(
            run, "py", return_value=({}, json.dumps(guard).encode(), b"")
        ):
            with self.assertRaisesRegex(RuntimeError, "shadow"):
                run.cpu_environment("full")

    def test_instrumented_environment_is_process_local(self):
        run = driver.Run(self.root)
        run.test_python, run.source = self.root / "python", self.root
        run.full_env = {"PYTHONPATH": "docs_src"}
        guard = {"existing_hooks": [], "trace": False, "profile": False}
        with patch.object(
            run, "py", return_value=({}, json.dumps(guard).encode(), b"")
        ):
            env, receipts = run.cpu_environment("full")
        self.assertEqual(run.full_env, {"PYTHONPATH": "docs_src"})
        self.assertEqual(env["HOBL_CPU_RECEIPT_DIR"], str(receipts))
        self.assertEqual(
            env["PYTHONPATH"].split(os.pathsep), [str(cpu_audit.HOOK), "docs_src"]
        )

    def test_only_instrumented_command_captures_native_entry_pid(self):
        run = driver.Run(self.root)
        receipts = run.upload / "smoke-worker-cpu"
        receipts.mkdir()
        env = {
            **run.env,
            "PYTHONPATH": str(cpu_audit.HOOK),
            "HOBL_CPU_RECEIPT_DIR": str(receipts),
        }
        with patch.object(driver.subprocess, "Popen") as launch:
            process = launch.return_value.__enter__.return_value
            process.pid, process.wait.return_value = 101, 0
            row, _, _ = run.command(
                "cpu-hook-smoke", ["mock"], env=env, cpu_receipt=True
            )
        self.assertEqual(row["entry_pid"], 101)
        self.assertFalse(row["performance_eligible"])
