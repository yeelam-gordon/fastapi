"""Fixture-only counterexamples; passing tests reproduce acceptance defects."""

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

PROTOCOL = Path(__file__).resolve().parents[2] / "protocol"
sys.path.insert(0, str(PROTOCOL))

compare = importlib.import_module("compare_pairs")
measure = importlib.import_module("measure_pairs")
report = importlib.import_module("test_pairs").report


class ReviewCounterexamples(unittest.TestCase):
    def test_missing_or_failed_reused_caller_receipts_still_claim_parity(self):
        for receipt in (None, {"status": "failed", "environment": "reused"}):
            with self.subTest(receipt=receipt):
                windows, mac = report("Windows"), report("Darwin")
                for evidence in (windows, mac):
                    for sample in evidence["samples"]:
                        if sample["variant"] != "B" and receipt is not None:
                            sample["wrapper_report"] = receipt
                result = compare.compare(windows, mac)
                self.assertTrue(result["sdk_caller_isolated_sample_parity"])

    def test_empty_code_identities_still_claim_parity(self):
        windows, mac = report("Windows"), report("Darwin")
        for evidence in (windows, mac):
            evidence["tool_hashes"] = {}
            evidence["harness_revision"] = ""
            evidence["runtime"]["executable_sha256"] = "not-a-sha256"
            evidence["runtime"]["shared_library_sha256"] = "not-a-sha256"
            # Fixture intentionally has no uv executable hash or binary receipt.
        self.assertTrue(
            compare.compare(windows, mac)["sdk_caller_isolated_sample_parity"]
        )

    def test_successful_fast_parent_never_checks_or_kills_owned_child(self):
        process, child, owner = Mock(), Mock(), Mock()
        process.pid, child.pid = 42, 43
        process.poll.return_value = 0
        process.wait.return_value = 0
        child.is_running.return_value = True
        child.status.return_value = "running"
        owner.children.return_value = [child]
        psutil = types.SimpleNamespace(
            Process=Mock(return_value=owner),
            NoSuchProcess=LookupError,
            Error=RuntimeError,
            STATUS_ZOMBIE="zombie",
        )
        with (
            patch.dict(sys.modules, {"psutil": psutil}),
            patch.object(Path, "open", mock_open()),
            patch.object(measure.subprocess, "Popen", return_value=process),
            patch.object(measure.time, "perf_counter", side_effect=[0, 0.01]),
        ):
            result = measure.run(["fixture"], Path("fixture.log"), Path("."), {})
        self.assertTrue(measure.succeeded(result))
        owner.children.assert_not_called()
        child.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
