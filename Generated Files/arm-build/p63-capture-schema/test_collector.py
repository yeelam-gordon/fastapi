"""Synthetic controls only: never launch WPR, a Job, decoder, build, or API call."""

import base64
import contextlib
import dataclasses
import hashlib
import io
import json
import math
import shutil
import subprocess
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import collector as source


@dataclasses.dataclass
class FakeReceipt:
    succeeded: bool = True
    errors: tuple = ()


class FakeGuardian:
    def __init__(self):
        self.commands = []
        self.fail_start = self.fail_stop = self.wrong_context = False
        self.drops = 0

    def __call__(self, argv, *, cwd, env, stdout_path, stderr_path, timeout):
        self.commands.append((argv, timeout))
        instance = argv[-1]
        text = ""
        if "-Phase" in argv and argv[-1] == "Preflight":
            source.durable(
                Path(cwd) / "preflight.json",
                {
                    "admin": True,
                    "native_arm": True,
                    "module_version": "1.0",
                    "module_sha256": source.MODULE_SHA,
                },
            )
        elif "-Phase" in argv and argv[-1] == "Decode":
            window = source.read_json(Path(cwd) / "build-window.json")
            report = report_fixture()
            report["Overview"] = {
                "StartTime": window["begin_filetime"] - 1,
                "EndTime": window["end_filetime"] + 1,
            }
            report["TopScans"][0].update(
                StartTime=window["begin_filetime"] + 1,
                EndTime=window["begin_filetime"] + 2,
                Duration=1,
                Path=str(Path(cwd) / "work" / "file"),
            )
            source.durable(Path(cwd) / "raw-report.json", report)
        elif "-profiledetails" in argv:
            text = (
                f"Profile : {source.PROFILE_NAME}\n"
                "Number of Buffers : 32\nBuffer Size (KB) : 1024\n"
                "Number of Buffers : 32\nBuffer Size (KB) : 1024\nMicrosoft-Antimalware-Engine\n"
            )
        elif "-status" in argv and "profiles" in argv:
            profile = (
                "Other.Light.Memory" if self.wrong_context else source.PROFILE_NAME
            )
            text = f"Profile : {profile}\nLogging mode : Memory\nDropped event : {self.drops}\n"
        elif "-status" in argv:
            prefix = "WPR_initiated_" + instance + "_"
            text = (
                f"Collector Name : {prefix}WPR System Collector\nBuffer Size (KB) : 1024\nNumber of Buffers : 32\nEvents Lost : 0\nProcessThread\n"
                f"Collector Name : {prefix}Owned Engine Memory\nBuffer Size (KB) : 1024\nNumber of Buffers : 32\nEvents Lost : 0\nMicrosoft-Antimalware-Engine\n"
            )
        elif "-stop" in argv and not self.fail_stop:
            Path(argv[argv.index("-stop") + 1]).write_bytes(b"synthetic-not-an-etl")
        Path(stdout_path).write_text(text, encoding="utf-8")
        Path(stderr_path).write_text("", encoding="utf-8")
        return FakeReceipt(
            not (
                ("-start" in argv and self.fail_start)
                or ("-stop" in argv and self.fail_stop)
            )
        )


def report_fixture():
    return {
        "Overview": {"StartTime": 50, "EndTime": 250},
        "TopScans": [
            {
                "StartTime": 110,
                "EndTime": 130,
                "Duration": 20,
                "Path": r"C:\owned\work\file",
                "ScanType": "File",
            }
        ],
    }


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = source.HERE / ".fixtures" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        source.durable(
            self.root / "hosted-receipt.json",
            {"run_id": "123", "job_id": 456, "head_sha": "a" * 40},
        )
        self.fake = FakeGuardian()
        self.controller = source.Controller(
            self.root, self.fake, {"SYSTEMROOT": r"C:\Windows"}, clock=lambda: 0
        )

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_default_does_not_read_authority_or_execute(self):
        output = io.StringIO()
        with patch.object(
            source, "hosted_receipt", side_effect=AssertionError("not allowed")
        ):
            with contextlib.redirect_stdout(output):
                code = source.main([])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())["collection_executed"])
        self.assertEqual(self.fake.commands, [])

    def test_local_and_env_only_hosting_refused(self):
        with patch.object(source.platform, "system", return_value="Windows"):
            with patch.object(source.platform, "machine", return_value="ARM64"):
                with self.assertRaises((source.Stop, KeyError)):
                    source.hosted_receipt(
                        {},
                        {"GITHUB_ACTIONS": "true"},
                        get=lambda *a: self.fail("no network"),
                    )
        self.assertEqual(self.fake.commands, [])

    def test_positive_capture_is_one_build_and_one_owned_stop(self):
        calls = []
        self.controller.capture(lambda timeout: calls.append(timeout))
        self.assertEqual(len(calls), 1)
        self.assertLessEqual(calls[0], 20)
        self.assertEqual(sum("-start" in argv for argv, _ in self.fake.commands), 1)
        self.assertEqual(sum("-stop" in argv for argv, _ in self.fake.commands), 1)
        stop = next(
            (argv, timeout) for argv, timeout in self.fake.commands if "-stop" in argv
        )
        self.assertEqual(stop[1], 60)
        self.assertIn("-skipPdbGen", stop[0])
        self.assertTrue((self.root / "ready.json").is_file())
        self.assertTrue((self.root / "stopped.json").is_file())
        for argv, _ in self.fake.commands:
            self.assertEqual(argv[-2:], ["-instancename", self.controller.instance])
            self.assertNotIn("-filemode", argv)
            self.assertNotIn("-cancel", argv)

    def test_existing_start_never_stops_or_cancels(self):
        self.fake.fail_start = True
        with self.assertRaisesRegex(source.Stop, "OWNED_COMMAND_FAILED"):
            self.controller.capture(lambda timeout: self.fail("must not build"))
        self.assertEqual(len(self.fake.commands), 1)
        self.assertFalse((self.root / "started.json").exists())

    def test_controller_cannot_capture_twice(self):
        self.controller.capture(lambda timeout: None)
        previous = len(self.fake.commands)
        with self.assertRaisesRegex(source.Stop, "CAPTURE_ATTEMPT_ALREADY_USED"):
            self.controller.capture(lambda timeout: self.fail("no second build"))
        self.assertEqual(len(self.fake.commands), previous)

    def test_unproven_named_context_never_builds_or_stops(self):
        self.fake.wrong_context = True
        with self.assertRaisesRegex(source.Stop, "NAMED_PROFILE_OR_LOSS_UNPROVEN"):
            self.controller.capture(lambda timeout: self.fail("must not build"))
        self.assertFalse(any("-stop" in argv for argv, _ in self.fake.commands))

    def test_drop_counter_rejects_diagnostic_but_stops_matching_owned_session(self):
        self.fake.drops = 1
        with self.assertRaisesRegex(source.Stop, "NAMED_PROFILE_OR_LOSS_UNPROVEN"):
            self.controller.capture(lambda timeout: self.fail("must not build"))
        self.assertEqual(sum("-stop" in argv for argv, _ in self.fake.commands), 1)

    def test_durable_context_tamper_prevents_stop(self):
        self.controller.start()
        (self.root / "started.json").write_text('{"foreign":true}')
        with self.assertRaisesRegex(source.Stop, "DURABLE_OWNERSHIP_MISMATCH"):
            self.controller.stop()
        self.assertFalse(any("-stop" in argv for argv, _ in self.fake.commands))

    def test_build_timeout_preserves_first_failure_with_safe_stop(self):
        def build(timeout):
            raise source.Stop("BUILD_TIMEOUT")

        with self.assertRaisesRegex(source.Stop, "BUILD_TIMEOUT"):
            self.controller.capture(build)
        self.assertEqual(sum("-stop" in argv for argv, _ in self.fake.commands), 1)

    def test_loss_observed_after_build_is_failure_after_owned_stop(self):
        def build(timeout):
            self.fake.drops = 1

        with self.assertRaisesRegex(source.Stop, "CAPTURE_LOSS_REPORTED"):
            self.controller.capture(build)
        self.assertTrue((self.root / "stopped.json").is_file())

    def test_elapsed_requested_window_is_not_silently_accepted(self):
        now = [0]
        self.controller.clock = lambda: now[0]

        def build(timeout):
            now[0] = 31

        with self.assertRaisesRegex(source.Stop, "REQUESTED_RECORDING_WINDOW_EXCEEDED"):
            self.controller.capture(build)
        self.assertEqual(sum("-stop" in argv for argv, _ in self.fake.commands), 1)

    def test_failed_merge_is_not_retried_or_cancelled(self):
        self.fake.fail_stop = True
        with self.assertRaisesRegex(source.Stop, "OWNED_COMMAND_FAILED"):
            self.controller.capture(lambda timeout: None)
        self.controller.stop()
        self.assertEqual(sum("-stop" in argv for argv, _ in self.fake.commands), 1)
        self.assertFalse(any("-cancel" in argv for argv, _ in self.fake.commands))

    def test_post_stop_size_guard_is_not_a_write_cap(self):
        with patch.object(source, "LIMIT", 1):
            with self.assertRaisesRegex(source.Stop, "POST_STOP_OUTPUT_REJECTED"):
                self.controller.capture(lambda timeout: None)
        self.assertTrue((self.root / "raw.etl").exists())

    def test_synthetic_complete_projection_positive_finite_and_pathless(self):
        result = source.project(
            report_fixture(), r"C:\owned", 100, 200, complete_coverage=True
        )
        self.assertEqual(
            result, {"observed_owned_path_scans": 1, "observed_scan_duration_ms": 0.002}
        )
        self.assertTrue(math.isfinite(result["observed_scan_duration_ms"]))
        self.assertNotIn("Path", json.dumps(result))

    def test_actual_controller_cannot_invent_complete_coverage(self):
        with self.assertRaisesRegex(source.Stop, "COMPLETE_CAPTURE_COVERAGE_UNPROVEN"):
            source.project(report_fixture(), r"C:\owned", 100, 200)

    def test_unknown_secret_field_rejected_and_descriptor_is_hash_only(self):
        report = report_fixture()
        report["TopScans"][0]["PRIVATE_SECRET_PROPERTY"] = "PRIVATE_SECRET_VALUE"
        with self.assertRaisesRegex(source.Stop, "SCAN_SCHEMA"):
            source.project(report, r"C:\owned", 100, 200, complete_coverage=True)
        digest = source.descriptor(report)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertNotIn("PRIVATE", digest)

    def test_nonfinite_scan_value_rejected(self):
        report = report_fixture()
        report["TopScans"][0]["Duration"] = math.inf
        with self.assertRaisesRegex(source.Stop, "SCAN_TIME_TYPE_OR_RANGE"):
            source.project(report, r"C:\owned", 100, 200, complete_coverage=True)

    def test_duplicate_json_field_cannot_override_owned_path(self):
        path = self.root / "duplicate.json"
        path.write_text('{"Path":"outsider","Path":"owned"}')
        with self.assertRaisesRegex(source.Stop, "DUPLICATE_JSON_FIELD"):
            source.read_json(path)

    def test_outsider_prefix_is_not_owned(self):
        report = report_fixture()
        report["TopScans"][0]["Path"] = r"C:\owned-sibling\private"
        with self.assertRaisesRegex(source.Stop, "NO_OBSERVED_OWNED_PATH_SCANS"):
            source.project(report, r"C:\owned", 100, 200, complete_coverage=True)

    def test_top_n_or_empty_never_becomes_zero_cost(self):
        report = report_fixture()
        report["TopScans"] = []
        with self.assertRaisesRegex(source.Stop, "MISSING_OR_TOP_N_COVERAGE"):
            source.project(report, r"C:\owned", 100, 200, complete_coverage=True)
        report["TopScans"] = [report_fixture()["TopScans"][0]] * source.TOP_N
        with self.assertRaisesRegex(source.Stop, "MISSING_OR_TOP_N_COVERAGE"):
            source.project(report, r"C:\owned", 100, 200, complete_coverage=True)

    def test_report_envelope_must_contain_build_interval(self):
        report = report_fixture()
        report["Overview"]["StartTime"] = 101
        with self.assertRaisesRegex(source.Stop, "REPORT_TIME_ENVELOPE_UNPROVEN"):
            source.project(report, r"C:\owned", 100, 200, complete_coverage=True)

    def test_profile_is_identical_to_reviewed_memory_source(self):
        self.assertEqual(source.sha(self.controller.profile), source.PROFILE_SHA)

    def test_documented_live_status_without_counts_and_wrong_optional_count(self):
        instance = self.controller.instance
        profiles = (
            "Dropped event : 0\nLogging mode : Memory\n"
            "Profile : OwnedEngineProcess.Light.Memory\n"
        )
        collectors = (
            f"Collector Name : WPR_initiated_{instance}_WPR System Collector\n"
            "Buffer Size (KB) : 1024\nEvents Lost : 0\nSystem Keywords\nProcessThread\n"
            f"Collector Name : WPR_initiated_{instance}_Owned Engine Memory\n"
            "Buffer Size (KB) : 1024\nEvents Lost : 0\nProviders\n"
            "Microsoft-Antimalware-Engine: : 0xff\n"
        )
        self.assertTrue(source.named_status(profiles, collectors, instance))
        with self.assertRaisesRegex(source.Stop, "NAMED_COLLECTOR_CONTEXT_UNPROVEN"):
            source.named_status(
                profiles, collectors + "Number of Buffers : 64\n", instance
            )
        with self.assertRaisesRegex(source.Stop, "NAMED_COLLECTOR_CONTEXT_UNPROVEN"):
            source.named_status(
                profiles, collectors + "Number of Buffers : unknown\n", instance
            )

    def test_fake_pipeline_orders_setup_capture_oracle_decode_and_fails_unknown_coverage(
        self,
    ):
        phases = []
        env = {
            "SYSTEMROOT": r"C:\Windows",
            "WINDIR": r"C:\Windows",
            "COMSPEC": r"C:\Windows\System32\cmd.exe",
        }

        def fake_prepare(plan, root):
            self.assertTrue((root / "preflight.json").is_file())
            phases.append("setup")

            def build(controller, timeout):
                self.assertTrue((root / "ready.json").is_file())
                phases.append("one-build")

            def oracle():
                self.assertTrue((root / "stopped.json").is_file())
                phases.append("oracle")

            return env, build, oracle

        with patch.dict(source.os.environ, env):
            with patch.object(source, "prepare", side_effect=fake_prepare):
                with patch.object(source.time, "time_ns", side_effect=[10000, 20000]):
                    with self.assertRaisesRegex(
                        source.Stop, "COMPLETE_CAPTURE_COVERAGE_UNPROVEN"
                    ):
                        source.execute({}, {}, self.root, self.fake)
        self.assertEqual(phases, ["setup", "one-build", "oracle"])
        self.assertTrue((self.root / "artifact-oracle.json").is_file())
        self.assertTrue((self.root / "schema-descriptor.json").is_file())
        self.assertEqual(sum("-start" in argv for argv, _ in self.fake.commands), 1)

    def test_authenticated_api_context_positive_and_self_hosted_refusal(self):
        authority = {
            "approved": True,
            "scope": "P63_ONE_EPHEMERAL_ATTEMPT",
            "repository": source.REPOSITORY,
            "workflow_id": 400167398,
            "run_id": "123",
            "run_attempt": "1",
            "job_id": 456,
            "job_timeout_minutes": 8,
            "accepted_transient_overshoot": True,
            "expires": time.time() + 300,
            "head_sha": "a" * 40,
            "ref": "refs/heads/perf/conditional",
        }
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "a" * 40,
            "RUNNER_NAME": "fixture",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://fixture.actions.githubusercontent.com/idtoken",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "SYNTHETIC",
            "GITHUB_TOKEN": "SYNTHETIC",
        }
        claims = {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "p63-123-456",
            "runner_environment": "github-hosted",
            "repository": source.REPOSITORY,
            "run_id": "123",
            "run_attempt": "1",
            "event_name": "workflow_dispatch",
            "ref": authority["ref"],
            "workflow_sha": "a" * 40,
            "nbf": time.time() - 10,
            "exp": time.time() + 300,
            "check_run_id": "789",
        }

        def fake_get(url, credential):
            if url.endswith("/runs/123"):
                return {
                    "workflow_id": 400167398,
                    "head_sha": "a" * 40,
                    "event": "workflow_dispatch",
                    "run_attempt": 1,
                    "path": ".github/workflows/arm-build-experiment.yml",
                }
            if url.endswith("/jobs/456"):
                return {
                    "run_id": 123,
                    "run_attempt": 1,
                    "status": "in_progress",
                    "check_run_url": "https://api.github.com/check-runs/789",
                    "runner_name": "fixture",
                    "labels": ["windows-11-arm"],
                }
            return {"value": "SYNTHETIC_JWT"}

        with patch.object(source.platform, "system", return_value="Windows"):
            with patch.object(source.platform, "machine", return_value="ARM64"):
                with patch.object(source.os, "cpu_count", return_value=4):
                    with patch.object(source, "signed_claims", return_value=claims):
                        self.assertEqual(
                            source.hosted_receipt(authority, env, fake_get)["job_id"],
                            456,
                        )
                        claims["runner_environment"] = "self-hosted"
                        with self.assertRaisesRegex(
                            source.Stop, "HOSTED_IDENTITY_MISMATCH"
                        ):
                            source.hosted_receipt(authority, env, fake_get)

    def test_unexpected_error_is_durable_nonzero_without_private_echo(self):
        plan = self.root / "plan.json"
        authority = self.root / "authority.json"
        source.durable(plan, {})
        source.durable(authority, {"plan_sha256": source.sha(plan)})
        output = io.StringIO()
        with patch.object(
            source, "hosted_receipt", return_value={"run_id": "123", "job_id": 456}
        ):
            with patch.object(source, "load_guardian", return_value=self.fake):
                with patch.object(
                    source,
                    "execute",
                    side_effect=RuntimeError("PRIVATE_SECRET_PAYLOAD"),
                ):
                    # The mocked guardian path is still required by the normal caller.
                    plan.write_text(
                        json.dumps(
                            {
                                "published_guardian": "synthetic",
                                "source_sha256": {
                                    name: source.sha(source.HERE / name)
                                    for name in (
                                        "collector.py",
                                        "private_report.ps1",
                                        "private_root.ps1",
                                        "ENGINE-PROCESS-MEMORY.wprp",
                                    )
                                },
                                "job_workspace": str(self.root.resolve()),
                            }
                        )
                    )
                    authority.write_text(
                        json.dumps(
                            {
                                "plan_sha256": source.sha(plan),
                                "job_workspace": str(self.root.resolve()),
                            }
                        )
                    )

                    def fake_private_root(workspace):
                        root = workspace / ".p63-private-synthetic"
                        root.mkdir()
                        return root

                    with patch.dict(
                        source.os.environ,
                        {"GITHUB_WORKSPACE": str(self.root.resolve())},
                    ):
                        with patch.object(
                            source, "private_root", side_effect=fake_private_root
                        ):
                            with contextlib.redirect_stdout(output):
                                code = source.main(
                                    ["--collect", str(authority), str(plan)]
                                )
        self.assertEqual(code, 2)
        public = json.loads(output.getvalue())
        self.assertEqual(public["category"], "PRIVATE_UNEXPECTED_FAILURE")
        self.assertNotIn("PRIVATE_SECRET_PAYLOAD", output.getvalue())
        self.assertEqual(
            len(list(self.root.glob(".p63-private-*/public-result.json"))), 1
        )

    def test_same_authority_different_cwd_cannot_repeat_job_attempt(self):
        plan = self.root / "job-plan.json"
        authority = self.root / "job-authority.json"
        workspace = str(self.root.resolve())
        source.durable(
            plan,
            {
                "job_workspace": workspace,
                "published_guardian": "synthetic",
                "source_sha256": {
                    name: source.sha(source.HERE / name)
                    for name in (
                        "collector.py",
                        "private_report.ps1",
                        "private_root.ps1",
                        "ENGINE-PROCESS-MEMORY.wprp",
                    )
                },
            },
        )
        source.durable(
            authority, {"job_workspace": workspace, "plan_sha256": source.sha(plan)}
        )
        first = self.root / "first-cwd"
        second = self.root / "second-cwd"
        first.mkdir()
        second.mkdir()
        output = io.StringIO()
        with patch.dict(source.os.environ, {"GITHUB_WORKSPACE": workspace}):
            with patch.object(
                source, "hosted_receipt", return_value={"run_id": "123", "job_id": 456}
            ):
                with patch.object(
                    source,
                    "private_root",
                    side_effect=source.Stop("PRIVATE_ROOT_BOOTSTRAP_FAILED"),
                ) as bootstrap:
                    with patch.object(source, "load_guardian") as guardian:
                        with contextlib.redirect_stdout(output):
                            with contextlib.chdir(first):
                                self.assertEqual(
                                    source.main(
                                        ["--collect", str(authority), str(plan)]
                                    ),
                                    2,
                                )
                            with contextlib.chdir(second):
                                self.assertEqual(
                                    source.main(
                                        ["--collect", str(authority), str(plan)]
                                    ),
                                    2,
                                )
        bootstrap.assert_called_once()
        guardian.assert_not_called()
        self.assertEqual(
            json.loads(output.getvalue().splitlines()[-1])["category"],
            "CAPTURE_ATTEMPT_ALREADY_USED",
        )
        self.assertTrue((self.root / ".p63-attempt-123-456.json").is_file())
        self.assertEqual(list(first.iterdir()), [])
        self.assertEqual(list(second.iterdir()), [])
        self.assertEqual(self.fake.commands, [])

    def test_job_workspace_alias_and_reparse_are_refused(self):
        alias = str(self.root.resolve()) + r"\..\elsewhere"
        with self.assertRaisesRegex(source.Stop, "JOB_WORKSPACE_ALIAS"):
            source.job_workspace(
                {"job_workspace": alias},
                {"job_workspace": alias},
                {"GITHUB_WORKSPACE": alias},
            )
        workspace = str(self.root.resolve())
        with patch.object(source.Path, "is_junction", return_value=True):
            with self.assertRaisesRegex(source.Stop, "JOB_WORKSPACE_REPARSE"):
                source.job_workspace(
                    {"job_workspace": workspace},
                    {"job_workspace": workspace},
                    {"GITHUB_WORKSPACE": workspace},
                )

    def test_acl_bootstrap_failure_never_persists_raw_streams(self):
        plan = self.root / "acl-plan.json"
        authority = self.root / "acl-authority.json"
        workspace = str(self.root.resolve())
        source.durable(
            plan,
            {
                "job_workspace": workspace,
                "published_guardian": "synthetic",
                "source_sha256": {
                    name: source.sha(source.HERE / name)
                    for name in (
                        "collector.py",
                        "private_report.ps1",
                        "private_root.ps1",
                        "ENGINE-PROCESS-MEMORY.wprp",
                    )
                },
            },
        )
        source.durable(
            authority, {"job_workspace": workspace, "plan_sha256": source.sha(plan)}
        )

        def failed_acl(argv, **kwargs):
            self.assertEqual(kwargs["timeout"], 10)
            self.assertTrue(kwargs["capture_output"])
            self.assertEqual(kwargs["env"]["NoDefaultCurrentDirectoryInExePath"], "1")
            self.assertNotIn("GH_TOKEN", kwargs["env"])
            self.assertNotIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", kwargs["env"])
            source.Path(argv[-1]).mkdir()
            return subprocess.CompletedProcess(
                argv, 2, b"PRIVATE_SECRET_PAYLOAD", b"PRIVATE_SECRET_ERROR"
            )

        output = io.StringIO()
        env = {
            "GITHUB_WORKSPACE": workspace,
            "SYSTEMROOT": r"C:\Windows",
            "WINDIR": r"C:\Windows",
            "COMSPEC": r"C:\Windows\System32\cmd.exe",
            "GH_TOKEN": "PRIVATE_CREDENTIAL",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "PRIVATE_OIDC",
        }
        with patch.dict(source.os.environ, env):
            with patch.object(
                source, "hosted_receipt", return_value={"run_id": "123", "job_id": 456}
            ):
                with patch.object(source.subprocess, "run", side_effect=failed_acl):
                    with patch.object(source, "load_guardian") as guardian:
                        with contextlib.redirect_stdout(output):
                            self.assertEqual(
                                source.main(["--collect", str(authority), str(plan)]), 2
                            )
        guardian.assert_not_called()
        self.assertEqual(
            json.loads(output.getvalue())["category"], "PRIVATE_ROOT_BOOTSTRAP_FAILED"
        )
        self.assertNotIn("PRIVATE_SECRET", output.getvalue())
        roots = list(self.root.glob(".p63-private-*"))
        self.assertEqual(len(roots), 1)
        self.assertEqual(list(roots[0].iterdir()), [])
        self.assertEqual(self.fake.commands, [])
        with patch.dict(source.os.environ, env):
            with patch.object(
                source.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("PRIVATE_SECRET", 10),
            ):
                with self.assertRaisesRegex(
                    source.Stop, "PRIVATE_ROOT_BOOTSTRAP_FAILED"
                ):
                    source.private_root(self.root)
        self.assertEqual(list(roots[0].iterdir()), [])

    def test_verified_acl_precedes_receipt_guardian_and_commands(self):
        plan = self.root / "order-plan.json"
        authority = self.root / "order-authority.json"
        workspace = str(self.root.resolve())
        source.durable(
            plan,
            {
                "job_workspace": workspace,
                "published_guardian": "synthetic",
                "source_sha256": {
                    name: source.sha(source.HERE / name)
                    for name in (
                        "collector.py",
                        "private_report.ps1",
                        "private_root.ps1",
                        "ENGINE-PROCESS-MEMORY.wprp",
                    )
                },
            },
        )
        source.durable(
            authority, {"job_workspace": workspace, "plan_sha256": source.sha(plan)}
        )
        phases = []

        def acl(argv, **kwargs):
            root = source.Path(argv[-1])
            self.assertFalse(root.exists())
            root.mkdir()
            self.assertEqual(list(root.iterdir()), [])
            phases.append("ACL_VERIFIED")
            return subprocess.CompletedProcess(
                argv, 0, b"P63_PRIVATE_ROOT_VERIFIED\n", b""
            )

        def guardian(path):
            phases.append("GUARDIAN_IMPORT")
            self.assertTrue(
                next(self.root.glob(".p63-private-*/hosted-receipt.json")).is_file()
            )
            return self.fake

        def execute(authority, plan, root, run_owned):
            phases.append("COMMANDS")
            self.assertTrue((root / "hosted-receipt.json").is_file())
            raise source.Stop("COMPLETE_CAPTURE_COVERAGE_UNPROVEN")

        env = {
            "GITHUB_WORKSPACE": workspace,
            "SYSTEMROOT": r"C:\Windows",
            "WINDIR": r"C:\Windows",
            "COMSPEC": r"C:\Windows\System32\cmd.exe",
        }
        with patch.dict(source.os.environ, env):
            with patch.object(
                source, "hosted_receipt", return_value={"run_id": "123", "job_id": 456}
            ):
                with patch.object(source.subprocess, "run", side_effect=acl):
                    with patch.object(source, "load_guardian", side_effect=guardian):
                        with patch.object(source, "execute", side_effect=execute):
                            with contextlib.redirect_stdout(io.StringIO()):
                                self.assertEqual(
                                    source.main(
                                        ["--collect", str(authority), str(plan)]
                                    ),
                                    2,
                                )
        self.assertEqual(phases, ["ACL_VERIFIED", "GUARDIAN_IMPORT", "COMMANDS"])

    def test_signed_oidc_claims_and_signature_tamper(self):
        def b64(data):
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        # Public synthetic RSA fixture, not a credential or real signing key.
        first, second = (1 << 1279) - 1, (1 << 2203) - 1
        modulus = first * second
        private_exponent = pow(65537, -1, (first - 1) * (second - 1))
        size = (modulus.bit_length() + 7) // 8
        header = b64(b'{"alg":"RS256","kid":"fixture"}')
        payload = b64(b'{"runner_environment":"github-hosted"}')
        data = (header + "." + payload).encode()
        digest = (
            bytes.fromhex("3031300d060960864801650304020105000420")
            + hashlib.sha256(data).digest()
        )
        encoded = b"\x00\x01" + b"\xff" * (size - len(digest) - 3) + b"\x00" + digest
        signature = pow(
            int.from_bytes(encoded, "big"), private_exponent, modulus
        ).to_bytes(size, "big")
        jwks = {
            "keys": [
                {
                    "kid": "fixture",
                    "kty": "RSA",
                    "n": b64(modulus.to_bytes(size, "big")),
                    "e": b64((65537).to_bytes(3, "big")),
                }
            ]
        }
        token = header + "." + payload + "." + b64(signature)
        self.assertEqual(
            source.signed_claims(token, jwks), {"runner_environment": "github-hosted"}
        )
        with self.assertRaisesRegex(source.Stop, "OIDC_SIGNATURE"):
            source.signed_claims(header + "." + b64(b"{}") + "." + b64(signature), jwks)


if __name__ == "__main__":
    unittest.main()
