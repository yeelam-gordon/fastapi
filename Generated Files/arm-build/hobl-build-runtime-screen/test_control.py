import argparse
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("build_control", Path(__file__).with_name("screen.py"))
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


class ControlTests(unittest.TestCase):
    def test_explicit_supplied_wheel_requires_hash_without_network_or_repatch(self):
        args = argparse.Namespace(source=Path("source"), output=Path("out"),
                                  uv=Path("uv.exe"),
                                  supplied_wheel=Path(control.WHEEL))
        for expected_hash, succeeds in ((control.WHEEL_SHA, True), ("wrong", False)):
            with self.subTest(succeeds=succeeds), \
                 patch.object(control, "prepare_source") as repatch, \
                 patch.object(control, "source_snapshot", return_value={}), \
                 patch.object(control, "save"), \
                 patch.object(control, "git", return_value=b"source-proof"), \
                 patch.object(control, "attest"), patch.object(Path, "mkdir"), \
                 patch.object(control.shutil, "copyfile"), \
                 patch.object(control, "digest", side_effect=["manifest", expected_hash, expected_hash]), \
                 patch.object(control.urllib.request, "urlopen") as network:
                if succeeds:
                    control.prepare(args)
                else:
                    with self.assertRaises(AssertionError):
                        control.prepare(args)
                network.assert_not_called()
                repatch.assert_not_called()

    def test_schedule_and_only_interpreter_treatment(self):
        self.assertEqual(control.schedule(), [
            ("stock", False), ("managed", False), ("stock", True),
            ("managed", True), ("managed", True), ("stock", True)])
        stock = control.command(Path("uv.exe"), Path("stock python.exe"), Path("out"))
        managed = control.command(Path("uv.exe"), Path("managed python.exe"), Path("out"))
        self.assertEqual([i for i in range(len(stock)) if stock[i] != managed[i]], [3])
        self.assertNotIn("--no-build-isolation", stock)
        self.assertEqual(stock[3], "stock python.exe")

    def test_first_build_failure_stops_cohort(self):
        args = argparse.Namespace(source=Path("source"), output=Path("out"),
                                  stock=Path(sys.executable), managed=Path(sys.executable),
                                  uv=Path("uv.exe"), smoke=False)
        with patch.object(control, "phase", side_effect=[{}, {}, RuntimeError("first build")]) as phase, \
             patch.object(control, "save"), patch.object(control, "load", return_value={}), \
             patch.object(control, "source_snapshot", return_value={}), \
             patch.object(Path, "mkdir"), patch.object(Path, "exists", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "first build"):
                control.worker(args)
            self.assertEqual(phase.call_count, 3)

    def test_failed_ownership_never_promotes_result(self):
        args = argparse.Namespace(action="run", source=Path("source"), output=Path("out"),
                                  stock=Path(sys.executable), managed=Path(sys.executable),
                                  uv=Path("uv.exe"), smoke=False)
        receipt = control.run_owned.__globals__["Receipt"](
            returncode=1, timed_out=False, command_wall=0, infrastructure_wall=0,
            ownership_established=True, survivors=False, cleanup_complete=True, errors=())
        with patch.object(control, "run_owned", return_value=receipt), \
             patch.object(control, "save") as save:
            with self.assertRaisesRegex(AssertionError, "Strict ownership"):
                control.main(args)
            self.assertEqual(save.call_count, 1)


if __name__ == "__main__":
    unittest.main()
