import argparse
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import hosted_source
import screen


class HostedScopeTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "RUNNER_OS": "Windows",
            "RUNNER_ARCH": "ARM64",
            "GITHUB_REPOSITORY": "yeelam-gordon/fastapi",
            "GITHUB_RUN_ATTEMPT": "1",
            "TEMP": "C:\\temp",
            "TMP": "C:\\temp",
        }
        self.parent = "hosted-cache-" + "a" * 32
        cache = Path("D:\\" + self.parent + "\\cache")
        self.args = argparse.Namespace(
            control_cache=cache,
            candidate_cache=cache,
            source=Path("C:\\original"),
            output=Path("C:\\evidence"),
            python=Path("C:\\runtime\\python.exe"),
            uv=Path("C:\\uv\\uv.exe"),
            wheels=Path("C:\\wheels"),
        )
        self.roots = {
            arm: Path(arm + ":\\" + self.parent + "\\source") for arm in ("C", "D")
        }
        self.scope = hosted_source.HostedSourceScope(
            {
                "Status": "Prepared",
                "BenchmarkEligible": True,
                "Reason": "OrdinaryReFS",
                "DiskNumber": 1,
                "DiskUniqueId": "unique-device",
                "CacheDirectory": str(cache),
            }
        )
        self.device = {
            "DiskNumber": 1,
            "DiskUniqueId": "unique-device",
            "BusType": "NVMe",
            "IsBoot": False,
            "IsSystem": False,
            "FileSystem": "ReFS",
            "Label": "HostedCache",
        }
        self.args.hosted_source_scope = self.scope

    def test_actual_scope_and_device_gates_fail_closed(self):
        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch.object(hosted_source.platform, "machine", return_value="ARM64"),
            patch.object(hosted_source.subprocess, "run") as query,
        ):
            query.return_value.stdout = json.dumps(self.device)
            self.scope.verify(self.args, self.roots)
            for name in self.environment:
                with self.subTest(gate=name), patch.dict(os.environ, {name: "wrong"}):
                    with self.assertRaises(RuntimeError):
                        self.scope.verify(self.args, self.roots)
            with patch.object(hosted_source.platform, "machine", return_value="AMD64"):
                with self.assertRaisesRegex(RuntimeError, "actual hosted"):
                    self.scope.verify(self.args, self.roots)
            for name, value in (
                ("DiskNumber", 2),
                ("DiskUniqueId", "other"),
                ("BusType", "SATA"),
                ("IsBoot", True),
                ("IsSystem", True),
                ("FileSystem", "NTFS"),
                ("Label", "Other"),
            ):
                with self.subTest(device=name):
                    query.return_value.stdout = json.dumps({**self.device, name: value})
                    with self.assertRaisesRegex(RuntimeError, "device binding changed"):
                        self.scope.verify(self.args, self.roots)

    def test_hosted_paths_require_explicit_scope_and_fixed_cache(self):
        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch.object(hosted_source.platform, "machine", return_value="ARM64"),
            patch.object(hosted_source.subprocess, "run") as query,
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(Path, "is_junction", return_value=False),
        ):
            query.return_value.stdout = json.dumps(self.device)
            screen.validate_source_paths(self.args, self.roots, (Path("C:\\runtime"),))
            for candidate in ("Q:\\other\\source", "D:\\other\\source"):
                with self.subTest(candidate=candidate):
                    with self.assertRaisesRegex(RuntimeError, "private equal-suffix"):
                        screen.validate_source_paths(
                            self.args,
                            {**self.roots, "D": Path(candidate)},
                            (Path("C:\\runtime"),),
                        )
            self.args.candidate_cache = Path("D:\\other\\cache")
            with self.assertRaisesRegex(RuntimeError, "common D cache"):
                screen.validate_source_paths(
                    self.args, self.roots, (Path("C:\\runtime"),)
                )
            self.args.candidate_cache = self.args.control_cache
            del self.args.hosted_source_scope
            with self.assertRaisesRegex(RuntimeError, "equal-suffix"):
                screen.validate_source_paths(
                    self.args, self.roots, (Path("C:\\runtime"),)
                )


if __name__ == "__main__":
    unittest.main()
