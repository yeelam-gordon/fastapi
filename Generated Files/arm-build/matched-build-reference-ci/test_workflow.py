"""Workflow source checks only; PyYAML is an existing validation tool."""

import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[3]


class WorkflowTests(unittest.TestCase):
    def test_owned_closure_has_no_step_deadline_shorter_than_job_budget(self):
        path = ROOT / ".github" / "workflows" / "matched-native-build-reference.yml"
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        with patch.object(time, "time", return_value=1005.0):
            elapsed = time.time() - 1000.0
        remaining = 900 - elapsed
        admitted_core = min(540, int(remaining - 355))
        closure = admitted_core + 25 + 240 + 25
        self.assertGreater(closure, 12 * 60)
        self.assertLess(closure, remaining)
        for name, job in workflow["jobs"].items():
            with self.subTest(job=name):
                steps = [
                    step
                    for step in job["steps"]
                    if step.get("name")
                    == "One default-I core then exact-target read-only raw verification"
                ]
                self.assertEqual(len(steps), 1)
                step_seconds = int(steps[0]["timeout-minutes"]) * 60
                self.assertGreaterEqual(step_seconds, int(job["timeout-minutes"]) * 60)
                self.assertGreaterEqual(step_seconds, closure)

    def test_only_two_conditional_native_jobs_no_aggregate_or_automated_trigger(self):
        path = ROOT / ".github" / "workflows" / "matched-native-build-reference.yml"
        source = path.read_text(encoding="utf-8")
        workflow = yaml.load(source, Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_call"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(workflow["jobs"]), {"windows", "darwin"})
        for name, runner in (("windows", "windows-11-arm"), ("darwin", "macos-15")):
            job = workflow["jobs"][name]
            self.assertEqual(job["runs-on"], runner)
            self.assertEqual(job["timeout-minutes"], "15")
            self.assertIn("github.repository == 'yeelam-gordon/fastapi'", job["if"])
            self.assertIn("github.run_attempt == '1'", job["if"])
            self.assertIn("github.event_name == 'workflow_dispatch'", job["if"])
            for step in job["steps"]:
                if "uses" in step:
                    self.assertRegex(step["uses"], r"^[^@]+@[0-9a-f]{40}$")
                    if step["uses"].startswith("actions/checkout@"):
                        self.assertEqual(step["with"]["persist-credentials"], "false")
                    if step["uses"].startswith("actions/upload-artifact@"):
                        self.assertEqual(step["if"], "always()")
                        self.assertEqual(step["with"]["include-hidden-files"], "true")
        self.assertNotRegex(
            source, r"(?i)continue-on-error|format-devdrive|workflow_run"
        )

    def test_storage_logging_projects_scalars_before_unchanged_provisioning(self):
        path = ROOT / ".github" / "workflows" / "matched-native-build-reference.yml"
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        steps = workflow["jobs"]["windows"]["steps"]
        storage = next(step for step in steps if step.get("id") == "storage")
        self.assertEqual(storage["timeout-minutes"], "1")
        source = storage["run"]
        self.assertNotIn("ConvertTo-Json -Depth 10", source)
        self.assertIn("ConvertTo-NvmeDiagnosticJson -Context (Get-NvmeContext)", source)
        self.assertIn("$diagnostic.Json", source)
        self.assertIn("$diagnostic.Utf8Bytes", source)
        self.assertLess(
            source.index("storage-before.json"),
            source.index("'Prepare-HostedNvme.ps1') -Provision"),
        )
        helper = Path(__file__).resolve().parent / "Storage-Diagnostic.ps1"
        text = helper.read_text()
        self.assertIn("ConvertTo-Json -Depth 5 -Compress -WarningAction Stop", text)
        self.assertIn("$bytes -gt 65536", text)

    def test_dispatcher_routes_scope_without_falling_into_full_workload(self):
        path = ROOT / ".github" / "workflows" / "arm-build-diagnostics.yml"
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertIn(
            "matched-native-build-reference",
            workflow["on"]["workflow_dispatch"]["inputs"]["platform"]["options"],
        )
        routed = workflow["jobs"]["matched-native-build-reference"]
        self.assertEqual(
            routed["uses"], "./.github/workflows/matched-native-build-reference.yml"
        )
        self.assertIn(
            "inputs.platform != 'matched-native-build-reference'",
            workflow["jobs"]["complete"]["if"],
        )

    def test_current_parent_and_release_cannot_grant_runtime_authority(self):
        here = Path(__file__).resolve().parent
        review = json.loads((here / "PARENT-REVIEW.json").read_text())
        release = json.loads((here / "RELEASE.json").read_text())
        self.assertIs(review["approved"], False)
        self.assertEqual(review["maximum_jobs"], 0)
        self.assertIsNone(review["expected_run_number"])
        self.assertIs(review["delegated_native_admission"], False)
        self.assertIs(release["hosted_raw_verifier_ready"], True)
        gate = (here / "Check-Release.ps1").read_text()
        self.assertIn("throw 'NOTADMITTED: zero approved jobs'", gate)
        self.assertIn("Separate finite one-run parent delegation required", gate)
        self.assertNotIn("Set-ExecutionPolicy", gate)
        self.assertNotIn("SOURCE_NOTREADY", gate)


if __name__ == "__main__":
    unittest.main()
