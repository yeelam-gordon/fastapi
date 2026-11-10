"""Both existing Windows entries validate themselves before any child operation."""

import argparse
import json
import shutil
import unittest
import uuid
from unittest.mock import patch

import bootstrap
import deploy


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.root = bootstrap.HERE / ("test-entry-" + uuid.uuid4().hex)
        (self.root / "matched-job-evidence").mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)

    def test_self_identity_precedes_stage_and_run_and_is_not_measured_sdk(self):
        for operation in ("stage", "run"):
            events = []
            args = argparse.Namespace(
                operation=operation,
                workspace=self.root,
                uv=self.root / "uv",
                controller_directory=r"C:\cache\Python\3.13.17\arm64",
                controller_version="3.13.17",
            )
            identity = {
                "version_info": [3, 13, 17],
                "prefix": args.controller_directory,
                "startup_ownership": "TRUSTED_BASELINE_UNOWNED_UNOBSERVED",
            }

            def self_identity(
                directory,
                version,
                *,
                events=events,
                controller_args=args,
                observation=identity,
            ):
                events.append("identity")
                self.assertEqual(
                    (directory, version),
                    (controller_args.controller_directory, "3.13.17"),
                )
                return observation

            def preparation(*args, events=events):
                events.append("prepare")
                path = self.root / "matched-evidence"
                path.mkdir()
                (path / "runtime-observed.json").write_text(
                    json.dumps(
                        {
                            "version_info": [3, 13, 15],
                            "executable": r"C:\private31315\Scripts\python.exe",
                        }
                    )
                )

            with (
                patch.object(
                    deploy.argparse.ArgumentParser, "parse_args", return_value=args
                ),
                patch.object(deploy.sys, "platform", "win32"),
                patch.object(
                    deploy.controller_identity,
                    "observe_self",
                    side_effect=self_identity,
                ),
                patch.object(
                    deploy,
                    "authorize",
                    side_effect=lambda env, events=events: events.append("authorize"),
                ),
                patch.object(deploy.bootstrap, "prepare", side_effect=preparation),
                patch.object(
                    deploy,
                    "run",
                    side_effect=lambda root, events=events: events.append("run"),
                ),
            ):
                deploy.main()
            self.assertEqual(
                events,
                ["identity", "authorize", "prepare" if operation == "stage" else "run"],
            )
            record = json.loads(
                (
                    self.root
                    / "matched-job-evidence"
                    / f"metadata-controller-{operation}.json"
                ).read_bytes()
            )
            self.assertEqual(record["identity"]["version_info"], [3, 13, 17])
            self.assertIn("NOT_OWNERSHIP_OR_MEASURED_SDK", record["scope"])
            self.assertNotIn("cleanup_complete", record)

    def test_identity_failure_before_first_command_never_calls_preparation(self):
        args = argparse.Namespace(
            operation="stage",
            workspace=self.root,
            uv=self.root / "uv",
            controller_directory="wrong",
            controller_version="3.13.17",
        )
        with (
            patch.object(
                deploy.argparse.ArgumentParser, "parse_args", return_value=args
            ),
            patch.object(deploy.sys, "platform", "win32"),
            patch.object(
                deploy.controller_identity,
                "observe_self",
                side_effect=ValueError("identity failed"),
            ),
            patch.object(deploy.bootstrap, "prepare") as prepare,
            self.assertRaisesRegex(ValueError, "identity failed"),
        ):
            deploy.main()
        prepare.assert_not_called()
        self.assertFalse((self.root / "matched-evidence").exists())


if __name__ == "__main__":
    unittest.main()
