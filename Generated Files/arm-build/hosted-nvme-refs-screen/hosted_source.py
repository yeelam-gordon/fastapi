"""Explicit hosted source/default-output entrypoint; no storage provisioning."""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import screen  # noqa: E402


class HostedSourceScope:
    def __init__(self, storage):
        self.storage = storage

    def verify(self, args, roots):
        expected = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "RUNNER_OS": "Windows",
            "RUNNER_ARCH": "ARM64",
            "GITHUB_REPOSITORY": "yeelam-gordon/fastapi",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        screen.require(
            sys.platform == "win32"
            and platform.machine().upper() == "ARM64"
            and all(os.environ.get(key) == value for key, value in expected.items()),
            "actual hosted fork Windows ARM attempt-one scope required",
        )
        storage = self.storage
        screen.require(
            storage.get("Status") == "Prepared"
            and storage.get("BenchmarkEligible") is True
            and storage.get("Reason") == "OrdinaryReFS"
            and type(storage.get("DiskNumber")) is int
            and bool(storage.get("DiskUniqueId")),
            "eligible ordinary ReFS device binding required",
        )
        cache = Path(storage["CacheDirectory"])
        screen.require(
            cache.drive == "D:"
            and cache.name == "cache"
            and re.fullmatch(r"hosted-cache-[0-9a-f]{32}", cache.parent.name)
            and args.control_cache == args.candidate_cache == cache
            and roots
            == {
                "C": Path("C:" + str(cache.parent / "source")[2:]),
                "D": cache.parent / "source",
            },
            "private equal-suffix source roots and common D cache required",
        )
        observation = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$ErrorActionPreference='Stop'; "
                "$p=@(Get-Partition -DriveLetter D -ErrorAction Stop); "
                "$v=@(Get-Volume -DriveLetter D -ErrorAction Stop); "
                "if($p.Count -ne 1 -or $v.Count -ne 1){throw 'Ambiguous D'}; "
                "$d=Get-Disk -Number $p[0].DiskNumber -ErrorAction Stop; "
                "@{DiskNumber=$d.Number;DiskUniqueId=$d.UniqueId;"
                "BusType=[string]$d.BusType;IsBoot=$d.IsBoot;IsSystem=$d.IsSystem;"
                "FileSystem=$v[0].FileSystem;Label=$v[0].FileSystemLabel}|ConvertTo-Json",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        device = json.loads(observation.stdout)
        screen.require(
            device["DiskNumber"] == storage["DiskNumber"]
            and device["DiskUniqueId"] == storage["DiskUniqueId"]
            and device["BusType"] == "NVMe"
            and device["IsBoot"] is False
            and device["IsSystem"] is False
            and device["FileSystem"] == "ReFS"
            and device["Label"] == "HostedCache",
            "prepared D filesystem/device binding changed",
        )
        for key in ("TEMP", "TMP"):
            screen.require(
                Path(os.environ.get(key, "")).drive == "C:",
                "common C TEMP/TMP required",
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("python", "uv", "source", "wheels", "output", "storage"):
        parser.add_argument(
            "--" + key, type=lambda value: Path(value).resolve(), required=True
        )
    parser.add_argument("--seconds", type=float, default=600)
    args = parser.parse_args()
    storage = screen.load(args.storage)
    args.control_cache = args.candidate_cache = Path(storage["CacheDirectory"])
    roots = {
        "C": Path("C:" + str(args.control_cache.parent / "source")[2:]),
        "D": args.control_cache.parent / "source",
    }
    args.hosted_source_scope = HostedSourceScope(storage)
    args.hosted_source_scope.verify(args, roots)
    screen.require(not roots["C"].parent.exists(), "fresh private C parent required")
    roots["C"].parent.mkdir()
    screen.main(args, live_roots=roots)


if __name__ == "__main__":
    main()
