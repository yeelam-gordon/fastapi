"""Independent caller collision and recorded-environment fixtures."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROTOCOL = Path(__file__).resolve().parents[2] / "protocol"
sys.path.insert(0, str(PROTOCOL))
spec = importlib.util.spec_from_file_location(
    "caller_fixture_tests", PROTOCOL / "test_isolated_build.py"
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
wrapper = fixtures.wrapper


class IndependentGuards(fixtures.WrapperTests):
    def test_report_and_working_path_collisions(self):
        cases = (
            ("source-report", "report", self.args.source / "report.json"),
            ("output-report", "report", self.args.out_dir / "report.json"),
            ("source-cache", "cache_dir", self.args.source / "cache"),
            ("output-cache", "cache_dir", self.args.out_dir / "cache"),
            ("source-wheels", "wheelhouse", self.args.source),
        )
        for label, name, value in cases:
            original = getattr(self.args, name)
            self.args.report = self.root / (label + ".json")
            setattr(self.args, name, value)
            with self.subTest(case=label), patch.object(wrapper, "run_process") as run:
                self.assertEqual(wrapper.execute(self.args), 1)
                run.assert_not_called()
            setattr(self.args, name, original)

    def test_identity_is_executed_and_environment_record_is_whitelisted(self):
        with (
            patch.dict(wrapper.os.environ, {"REVIEW_SENTINEL_SECRET": "not-a-secret"}),
            patch.object(wrapper, "run_process", side_effect=self.fake_process),
        ):
            self.assertEqual(wrapper.execute(self.args), 0)
        report = self.receipt()
        identity = next(p for p in report["phases"] if p["phase"] == "identity")
        self.assertIn("-I", identity["argv"])
        self.assertNotIn("-O", identity["argv"])
        self.assertIn("sys.prefix", identity["argv"][-1])
        self.assertIn("(3,13,15)", identity["argv"][-1])
        self.assertIn("'pdm-backend'", identity["argv"][-1])
        self.assertNotIn("REVIEW_SENTINEL_SECRET", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
