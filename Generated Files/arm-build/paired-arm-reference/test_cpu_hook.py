"""Finite no-test guards; do not activate a startup hook or burn CPU."""

import importlib.util
import json
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    "lf_cpu_format_guard",
    pathlib.Path(__file__).parent / "cpu-hook" / "sitecustomize.py",
)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class CpuFormatChecks(unittest.TestCase):
    def test_self_record_has_pid_argv_scope_and_finite_totals(self):
        record = hook.cpu_record(123, 45, ["python", "-m", "coverage"], 0.125, 0.25)
        self.assertEqual(json.loads(json.dumps(record))["pid"], 123)
        self.assertEqual(record["ppid"], 45)
        self.assertEqual(record["self_cpu_seconds"], 0.375)
        self.assertIn("excludes descendants", record["scope"])

    def test_invalid_or_unknown_counters_never_become_zero(self):
        for value in (None, float("nan"), float("inf"), -1, "unknown", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                hook.cpu_record(123, 45, ["python"], value, 0.0)

    def test_invalid_pid_and_argv_are_rejected(self):
        for pid, ppid, argv in ((0, 1, []), (1, -1, []), (1, 0, None)):
            with self.subTest(pid=pid, ppid=ppid), self.assertRaises(ValueError):
                hook.cpu_record(pid, ppid, argv, 0.0, 0.0)


if __name__ == "__main__":
    unittest.main()
