"""Pure hosted wiring and publication checks; no hosted or native activity."""

import contextlib
import io
import json
import os
import shutil
import unittest
import uuid
from unittest.mock import patch

import hosted


class HostedTests(unittest.TestCase):
    def setUp(self):
        self.root = hosted.HERE / ".fixtures" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.pins = hosted.collector.read_json(hosted.HERE / "source-pins.json")
        self.result = {
            "status": "UNKNOWN",
            "diagnostic_ready": False,
            "category": "COMPLETE_CAPTURE_COVERAGE_UNPROVEN",
            "source_sha256": self.pins["source_sha256"]["collector.py"],
        }

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_default_does_not_authorize_or_execute(self):
        output = io.StringIO()
        with patch.object(hosted, "run", side_effect=AssertionError("collection")):
            with contextlib.redirect_stdout(output):
                self.assertEqual(hosted.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())["collection_executed"])

    def test_exact_unknown_projection_rejects_private_fields_and_success(self):
        self.assertEqual(
            hosted.public_result(self.result, self.pins)["stage"],
            "CAPTURE_SCHEMA_UNKNOWN",
        )
        with self.assertRaises(hosted.collector.Stop):
            hosted.public_result({**self.result, "private_path": "secret"}, self.pins)
        with self.assertRaises(hosted.collector.Stop):
            hosted.public_result({**self.result, "category": "SECRET_TOKEN"}, self.pins)
        with self.assertRaises(hosted.collector.Stop):
            hosted.public_result({**self.result, "status": "PASS"}, self.pins)
        with self.assertRaises(hosted.collector.Stop):
            hosted.public_result({**self.result, "raw_etl_sha256": "secret"}, self.pins)
        with self.assertRaises(hosted.collector.Stop):
            hosted.public_result({**self.result, "source_sha256": "0" * 64}, self.pins)

    def test_current_unique_running_job_no_fallback(self):
        env = {"GITHUB_RUN_ID": "42", "GH_TOKEN": "private", "RUNNER_NAME": "owned"}
        job = {
            "id": 99,
            "name": "p63-capture-schema",
            "run_id": 42,
            "run_attempt": 1,
            "status": "in_progress",
            "runner_name": "owned",
            "labels": ["windows-11-arm"],
        }
        calls = []

        def get(url, token):
            calls.append((url, token))
            return {"total_count": 1, "jobs": [job]}

        self.assertEqual(hosted.current_job(env, get), 99)
        self.assertEqual(len(calls), 1)
        job["status"] = "queued"
        with self.assertRaises(hosted.collector.Stop):
            hosted.current_job(env, get)
        job["status"] = "in_progress"
        job["labels"].append("self-hosted")
        with self.assertRaises(hosted.collector.Stop):
            hosted.current_job(env, get)
        with self.assertRaises(hosted.collector.Stop):
            hosted.current_job(env, lambda *_: {"total_count": 2, "jobs": [job, job]})

    def test_one_invocation_private_authority_and_durable_nonzero(self):
        env = {
            "P63_AUTHORIZATION": hosted.SCOPE,
            "GITHUB_REPOSITORY": hosted.collector.REPOSITORY,
            "GITHUB_REF": "refs/heads/perf/arm-scan-schema",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "NoDefaultCurrentDirectoryInExePath": "1",
            "GITHUB_RUN_ID": "42",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_WORKSPACE": str(self.root.resolve()),
        }
        output = self.root / "public-result.json"
        plan = {"paths": "fixed-test-plan", "job_workspace": str(self.root.resolve())}

        def fake_main(argv):
            self.assertEqual(argv[0], "--collect")
            authority = hosted.collector.read_json(argv[1])
            self.assertEqual(authority["job_id"], 99)
            self.assertEqual(authority["plan_sha256"], hosted.collector.sha(argv[2]))
            self.assertEqual(authority["job_timeout_minutes"], 8)
            self.assertTrue(authority["accepted_transient_overshoot"])
            print(json.dumps(self.result))
            return 2

        with patch.dict(os.environ, env, clear=True):
            with patch.object(hosted, "plan_for", return_value=(plan, self.pins)):
                with patch.object(hosted, "current_job", return_value=99):
                    with patch.object(
                        hosted.collector, "main", side_effect=fake_main
                    ) as controller:
                        self.assertEqual(
                            hosted.run(self.root, self.root / "uv", output), 2
                        )
        controller.assert_called_once()
        self.assertEqual(
            hosted.collector.read_json(self.root / "exit-code.json"), {"exit_code": 2}
        )
        public = hosted.collector.read_json(output)
        self.assertEqual(public["category"], "COMPLETE_CAPTURE_COVERAGE_UNPROVEN")
        self.assertNotIn("paths", output.read_text())
        self.assertNotIn("authority", output.read_text())

    def test_unexpected_error_is_private_and_never_green(self):
        output = self.root / "public-result.json"
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(hosted.run(self.root, self.root / "uv", output), 2)
        self.assertEqual(
            hosted.collector.read_json(output)["category"], "HOSTED_INTEGRATION_FAILED"
        )
        self.assertNotIn("Traceback", output.read_text())


if __name__ == "__main__":
    unittest.main()
