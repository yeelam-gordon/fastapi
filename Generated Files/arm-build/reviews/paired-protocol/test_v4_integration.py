"""Frozen integration fixtures; no native lifecycle experiments or package builds."""

import ast
import importlib
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

PROTOCOL = Path(__file__).parent / "v4-scratch" / "Generated Files" / "arm-build" / "protocol"
sys.path.insert(0, str(PROTOCOL))
measure = importlib.import_module("measure_pairs")
compare = importlib.import_module("compare_pairs")
fixtures = importlib.import_module("test_pairs")


class IntegrationGates(unittest.TestCase):
    def test_real_frozen_inventory_includes_helper_with_raw_hash(self):
        inventory = measure.code_receipts()
        name = measure.PREFIX + "protocol/owned_process.py"
        self.assertIn(name, measure.REQUIRED_TOOL_INPUTS)
        self.assertEqual(inventory[name], measure.digest((PROTOCOL / "owned_process.py").read_bytes()))

    def test_owned_failures_rejected_by_controller_and_comparator(self):
        good = measure.Receipt(0, False, 6, 0.1, True, False, True, ())
        cases = (
            {"ownership_established": False}, {"survivors": True},
            {"cleanup_complete": False}, {"errors": ("owned cleanup failed",)},
            {"timed_out": True}, {"returncode": 1}, {"command_wall": None},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with patch.object(measure, "run_owned", return_value=replace(good, **changes)):
                    result = measure.run(["fixture"], Path("fixture.log"), Path("."), {})
                self.assertFalse(measure.succeeded(result))
                windows, mac = fixtures.report("Windows"), fixtures.report("Darwin")
                windows["samples"][0].update(result)
                with patch.object(measure, "tool_inventory", return_value=measure.REQUIRED_TOOL_INPUTS):
                    with self.assertRaises(ValueError):
                        compare.compare(windows, mac)

    def test_command_clock_excludes_only_precommand_infrastructure(self):
        receipt = measure.Receipt(0, False, 3, 0.4, True, False, True, ())
        with patch.object(measure, "run_owned", return_value=receipt) as runner:
            result = measure.run(["fixture"], Path("fixture.log"), Path("."), {})
        runner.assert_called_once()
        self.assertTrue(measure.succeeded(result))
        self.assertEqual(result["wall"], 3)
        self.assertEqual(result["infrastructure_wall"], 0.4)

    def test_wrapper_has_no_posix_detach_and_identity_requires_explicit_B(self):
        tree = ast.parse((PROTOCOL / "isolated_build.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "Popen":
                    self.assertFalse(any(k.arg in ("start_new_session", "process_group") for k in node.keywords))
        report = fixtures.report("Windows")
        sample = report["samples"][1]
        self.assertEqual(sample["wrapper_report"]["phases"][2]["argv"][1:4], ["-B", "-I", "-c"])
        self.assertEqual(sample["wrapper_report"]["phases"][3]["argv"][1:4], ["-B", "-E", "-s"])
        measure.validate_wrapper(sample, report, set())
        sample["wrapper_report"]["environment"]["identity"]["dont_write_bytecode"] = False
        with self.assertRaises(ValueError):
            measure.validate_wrapper(sample, report, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
