"""One canonical CLI case/one worker; separate local83 prospective qualification."""

import argparse
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from cli_identity import associate
from execution import environment, owned, runtime_snapshot
from local_preflight import local_metadata
from matched import HERE, verify_sourcepins
from matched_audit import native_copies, resource, source_gate
from screen import digest, load, save
from source_prepare import fresh_payload, owned_helpers


def worker(args):
    verify_sourcepins()
    before = runtime_snapshot(Path(sys.prefix))
    result = {"status": "ERROR", "cases": 1, "workers": 1, "ci_admission": False}
    try:
        local_metadata()
        source = args.output / "source"
        manifest = fresh_payload(args.source_repo, source)
        helper = args.output / "owned-helpers"
        owned_helpers(helper)
        shutil.copyfile(HERE / "full-coverage.toml", args.output / "full-coverage.toml")
        save(args.output / "source-before.json", manifest)
        import importlib.util

        rewrite = Path(importlib.util.find_spec("_pytest.assertion.rewrite").origin)
        ready = {"accepted": True, "mac_runtime_accepted": False}
        save(args.output / "readiness.json", ready)
        row = {
            "index": 1,
            "arm": "A",
            "folder": str(args.output),
            "source": str(source),
            "manifest": str(args.output / "source-before.json"),
            "helper": str(helper),
            "helper_sources": {path.name: digest(path) for path in helper.iterdir()},
        }
        env = environment(SimpleNamespace(output=args.output), row)
        env.update(FULL_SUITE="0", CHECK_FIXTURE="0")
        command = [
            sys.executable,
            str(helper / "bootstrap.py"),
            "run",
            "--rcfile",
            str(args.output / "full-coverage.toml"),
            "-m",
            "pytest",
            "tests/test_fastapi_cli.py::test_fastapi_cli",
            "-q",
            "-p",
            "no:pytest_cov",
            "-p",
            "resource_observer",
            "-p",
            "matched_policy",
            "-n",
            "1",
            "--dist=loadgroup",
            "--max-worker-restart=0",
            f"--basetemp={args.output / 'pytest-owned'}",
            f"--junitxml={args.output / 'junit.xml'}",
        ]
        owned(command, source, env, args.output, "one-canonical-cli", 60, native=True)
        cases = list(ET.parse(args.output / "junit.xml").getroot().iter("testcase"))
        if len(cases) != 1 or any(
            case.find(name) is not None
            for case in cases
            for name in ("error", "failure", "skipped")
        ):
            raise ValueError("Exactly one successful canonical CLI case required")
        identities = [load(path) for path in args.output.glob("identity-*.json")]
        resource(args.output, identities, 1)
        source_gate(
            row,
            {item["pid"] for item in identities},
            {"path": str(rewrite), "sha256": digest(rewrite)},
        )
        copies = native_copies(args.output)
        import coverage

        native_cli, shards = set(), []
        identity_pids = {item["pid"] for item in identities}
        for path in copies.glob(".coverage.*"):
            part = coverage.CoverageData(basename=str(path))
            part.read()
            match = re.search(r"\.pid(\d+)\.", path.name)
            if not match:
                raise ValueError("Native shard PID label absent")
            pid = int(match[1])
            shards.append({"name": path.name, "pid": pid})
            if pid not in identity_pids and part.lines(
                str(source / "fastapi" / "cli.py")
            ):
                native_cli.add(pid)
        events = [
            json.loads(line)
            for path in args.output.glob("events-*.jsonl")
            for line in path.read_text().splitlines()
        ]
        actual = [row for row in events if row["kind"] == "actual_cli_popen"]
        waited = [row for row in events if row["kind"] == "actual_cli_waited"]
        records = [
            load(args.output / f"cli-native-identity-{pid}.json") for pid in native_cli
        ]
        if any(record["namespace"] != str(args.output) for record in records):
            raise ValueError("Foreign native process namespace")
        for event in actual:
            if event["argv"][1:] != [
                "-m",
                "coverage",
                "run",
                "-m",
                "fastapi",
                "dev",
                "non_existent_file.py",
            ]:
                raise ValueError("Canonical CLI argv differs")
        if (
            len(actual) != 1
            or not native_cli
            or set(associate(actual, waited, records)) != native_cli
        ):
            raise ValueError(
                "One actual canonical CLI launch/native association required"
            )
        result.update(
            status="PASS_ONE_CLI_PROSPECTIVE_ONLY", association=records, shards=shards
        )
    finally:
        try:
            if runtime_snapshot(Path(sys.prefix)) != before:
                result["status"] = "ERROR"
                raise ValueError("Local runtime/cache provenance changed")
        finally:
            save(args.output / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if not args.output.is_relative_to(
        HERE.parents[4] / "arm-build" / "pipe-matched-ci-readiness"
    ):
        raise ValueError("New owned research output only")
    if args.worker:
        worker(args)
    else:
        verify_sourcepins()
        args.output.mkdir(exist_ok=False)
        owned(
            [
                sys.executable,
                "-B",
                str(Path(__file__)),
                "--worker",
                "--source-repo",
                str(args.source_repo.resolve()),
                "--output",
                str(args.output),
            ],
            HERE,
            os.environ.copy(),
            args.output,
            "cli-readiness-controller",
            120,
        )
