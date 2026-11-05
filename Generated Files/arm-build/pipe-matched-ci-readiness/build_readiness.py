"""Exactly one offline uv sdist then wheel; no test or CI admission path."""

import argparse
import os
import shutil
import sys
from pathlib import Path

from archive_headers import expected_headers, full_inventory, require_reference
from execution import BACKEND_SHA, owned, runtime_snapshot
from local_preflight import local_metadata
from matched import HERE
from screen import COMMON, digest, load, save
from source_prepare import fresh_payload

sys.path.insert(0, str(COMMON))
from artifact_gate import artifact_set
from prepare_uv import attest


def copy_uv_archives(directory, destination):
    paths = list(directory.iterdir())
    archives = [path for path in paths if path.name.endswith((".whl", ".tar.gz"))]
    control = directory / ".gitignore"
    if (
        len(archives) != 2
        or sum(path.suffix == ".whl" for path in archives) != 1
        or set(paths) != {*archives, control}
        or control.read_bytes() != b"*"
    ):
        raise ValueError("Unexpected uv distribution output/control file")
    destination.mkdir()
    for path in archives:
        target = destination / path.name
        shutil.copyfile(path, target)
        if digest(path) != digest(target):
            raise ValueError("Archive audit copy differs")
    return destination


def worker(args):
    before = runtime_snapshot(Path(sys.prefix))
    result = {
        "status": "ERROR",
        "build_commands": 0,
        "test_commands": 0,
        "ci_admission": False,
    }
    try:
        pending = load(HERE / "CLI-ASSOCIATION-PENDING.json")
        for name, expected in pending["prospective_source_sha256"].items():
            if digest(HERE / name) != expected:
                raise ValueError(f"Pending one-build source changed: {name}")
        local_metadata()
        attest(args.uv)
        uv_before = digest(args.uv)
        wheel = args.wheel_dir / "pdm_backend-2.5.0-py3-none-any.whl"
        if (
            digest(wheel) != BACKEND_SHA
            or len(list(args.wheel_dir.glob("pdm_backend-*.whl"))) != 1
        ):
            raise ValueError(
                "Exact nested qualified PDM wheel required; no duplicate/root fallback"
            )
        manifest = fresh_payload(args.source_repo, args.output / "source")
        shutil.copyfile(
            COMMON / "build-constraints.txt", args.output / "build-constraints.txt"
        )
        save(args.output / "source-before.json", manifest)
        save(
            args.output / "offline-inputs.json",
            {
                "wheel": str(wheel),
                "sha256": digest(wheel),
                "uv": str(args.uv),
                "uv_sha256": digest(args.uv),
            },
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(
                ("PYTHON", "PYTEST_", "PIP_", "UV_", "COVERAGE_", "COV_CORE_")
            )
        }
        temp = args.output / "temp"
        temp.mkdir()
        env.update(
            SOURCE_DATE_EPOCH="1700000000",
            UV_CACHE_DIR=str(args.output / "uv-cache"),
            UV_FIND_LINKS=args.wheel_dir.as_uri(),
            PIP_FIND_LINKS=args.wheel_dir.as_uri(),
            PIP_NO_INDEX="1",
            PIP_CONSTRAINT=(args.output / "build-constraints.txt").as_uri(),
            TEMP=str(temp),
            TMP=str(temp),
            TMPDIR=str(temp),
        )
        command = [
            str(args.uv),
            "build",
            "--python",
            sys.executable,
            "--no-python-downloads",
            "--offline",
            "--no-index",
            "--find-links",
            str(args.wheel_dir),
            "--build-constraints",
            str(args.output / "build-constraints.txt"),
        ]
        result["build_commands"] = 1
        receipt = owned(
            command,
            args.output / "source",
            env,
            args.output,
            "one-build",
            90,
            native=True,
        )
        log = (args.output / "one-build.stderr").read_text(encoding="utf-8")
        if (
            "Building source distribution" not in log
            or "Building wheel from source distribution" not in log
        ):
            raise ValueError("Full sdist then wheel-from-sdist phases required")
        artifacts = copy_uv_archives(
            args.output / "source" / "dist", args.output / "artifacts"
        )
        payload = artifact_set(artifacts, args.output / "source", manifest)
        headers = full_inventory(artifacts)
        require_reference(
            headers,
            expected_headers(load(HERE / "reference-artifacts.json"), sys.platform),
        )
        save(args.output / "archive-inventory.json", payload)
        save(args.output / "full-reference-headers.json", headers)
        if any(
            digest(args.output / "source" / name) != sha
            for name, sha in manifest.items()
        ):
            raise ValueError("Fresh canonical source changed")
        if digest(wheel) != BACKEND_SHA:
            raise ValueError("Offline backend input changed")
        if digest(args.uv) != uv_before:
            raise ValueError("Qualified native uv input changed")
        result.update(
            status="PASS_ONE_BUILD_ONLY_NOT_FULL_HOBL",
            native_seconds=(receipt.native_end_ns - receipt.native_start_ns) / 1e9,
        )
    finally:
        try:
            if runtime_snapshot(Path(sys.prefix)) != before:
                result["status"] = "ERROR"
                raise ValueError("Original runtime/cache changed")
        finally:
            save(args.output / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    for name in ("source_repo", "output", "uv", "wheel_dir"):
        setattr(args, name, getattr(args, name).resolve())
    if not args.output.is_relative_to(
        HERE.parents[4] / "arm-build" / "pipe-matched-ci-readiness"
    ):
        raise ValueError("New owned research output only")
    if args.worker:
        worker(args)
    else:
        args.output.mkdir(exist_ok=False)
        owned(
            [
                sys.executable,
                "-B",
                str(Path(__file__)),
                "--worker",
                "--source-repo",
                str(args.source_repo),
                "--output",
                str(args.output),
                "--uv",
                str(args.uv),
                "--wheel-dir",
                str(args.wheel_dir),
            ],
            HERE,
            os.environ.copy(),
            args.output,
            "one-build-controller",
            150,
        )
