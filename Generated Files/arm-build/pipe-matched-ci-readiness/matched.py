"""Source-only matched experiment contract; admission remains fail-closed."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = "864b569cf8453654fc3bc2c64108c0f644e2918c"
PROTOTYPE = "77ed2c0db74060b43187c35edf6d41af6e053b145d54a76223f42b31b9f1a95a"
FIXTURE = "6d2c11683dc2e41f6c35507ec58fe55a12f0c641999b3f00a0e83727b3d7ee2d"
BLOCKERS = (
    "Parent source review has not admitted this new dataset",
    "Actual Mac runtime readiness deferred to bounded pre-payload native/source checks",
    "No service-host measurements or physical/resource parity acceptance exist",
)


def plan():
    return {
        "dataset": "pipe-matched-ci-v1",
        "status": "SOURCE_ONLY_IMPLEMENTED_PENDING_REVIEW_NO_PARITY_CLAIM",
        "source_revision": SOURCE,
        "schedule": ["A1", "B1", "B2", "A2"],
        "hosts": {"windows-11-arm": 4, "macos-14": 3},
        "commands_total": {"build": 8, "covered_test": 8},
        "warmups": 0,
        "retries": 0,
        "attempt": 1,
        "job_seconds": 480,
        "queue_guard_seconds": 300,
        "final_audit_seconds": 120,
        "python": "3.13.15",
        "windows_python": "uv-managed --no-bin --no-registry",
        "macos_python": "setup-python arm64",
        "pins": {"local": 83, "ci_common": 82},
        "prototype_sha256": PROTOTYPE,
        "fixture_sha256": FIXTURE,
        "coverage": {
            "version": "7.17.0",
            "source": ["docs_src", "tests", "fastapi"],
            "dynamic_context": "test_function",
            "patch": ["subprocess", "_exit"],
            "parallel": True,
            "context": "",
            "files": 863,
            "contexts": 1409,
            "cases": 2643,
            "passed": 2513,
            "skipped": 130,
            "context_filter": False,
            "extra_omit": False,
        },
        "primary_question": "Windows B total <= position-matched Mac control B total in both orders",
        "secondary_question": "Windows B saves >=0.5s and >=1% in both orders without test regression",
        "timing": "sdist then wheel-from-sdist + full covered tests; setup/audit excluded and reported",
        "macos_B": "identity control; stock default selector/Kqueue in both arms",
        "windows_B": "exact frozen worker-only pipe; stock main and explicit constructors",
        "admission": False,
        "blockers": list(BLOCKERS),
        "limitations": [
            "Local 4LP is not physical-host or macOS proof",
            "Build variation is not the pipe optimization",
            "Unknown global resource counts; stock plus eleven limits remain explicit",
            "API close success is not instantaneous kernel object reclamation",
            "No cross-OS raw-map equality; only proven source-root normalization",
            "Old unmatched 32.233/25.317 timings are not causal controls",
            "Original closed 60s controller audit is unchanged; independent audit is separate",
        ],
    }


def command_plan(python, uv, source, output, workers):
    """Freeze argv only; this function never starts a subprocess."""
    source, output = Path(source), Path(output)
    if workers not in (3, 4):
        raise ValueError("Only the two draft ARM host worker counts are defined")
    return {
        "cwd": str(source),
        "build": [
            str(uv),
            "build",
            "--python",
            str(python),
            "--no-python-downloads",
            "--offline",
            "--build-constraints",
            str(output / "build-constraints.txt"),
            "--find-links",
            str(output / "wheels"),
        ],
        "test": [
            str(python),
            str(HERE / "bootstrap.py"),
            "run",
            "--rcfile",
            str(output / "full-coverage.toml"),
            "-m",
            "pytest",
            "tests",
            "-q",
            "-p",
            "no:pytest_cov",
            "-p",
            "resource_observer",
            "-p",
            "matched_policy",
            "-n",
            str(workers),
            "--dist=loadgroup",
            "--max-worker-restart=0",
            f"--basetemp={output / 'pytest-owned'}",
            f"--junitxml={output / 'junit.xml'}",
        ],
    }


def static_check():
    for name, expected in (
        ("prototype.py", PROTOTYPE),
        ("qualified-fixture.py", FIXTURE),
    ):
        actual = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Frozen source mismatch: {name}: {actual}")
    return plan()


def verify_sourcepins():
    root = HERE.parents[2]
    for name, value in json.loads((HERE / "SOURCEPINS.json").read_text())[
        "files"
    ].items():
        path = root.joinpath(*name.replace("\\", "/").split("/"))
        if (
            not path.is_file()
            or path.stat().st_size != value["bytes"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != value["sha256"]
        ):
            raise RuntimeError(f"NoParityClaim: reviewed source changed: {name}")


def admit():
    static_check()
    if os.environ.get("GITHUB_REPOSITORY") != "yeelam-gordon/fastapi":
        raise RuntimeError("Owned fork only")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise RuntimeError("Attempt 1 only")
    review_path = HERE / "PARENT-REVIEW.json"
    if not review_path.is_file():
        raise RuntimeError("NoParityClaim: parent source review is required")
    review = json.loads(review_path.read_text())
    if (
        review.get("approved") is not True
        or review.get("sourcepins_sha256")
        != hashlib.sha256((HERE / "SOURCEPINS.json").read_bytes()).hexdigest()
    ):
        raise RuntimeError("NoParityClaim: review is not SHA-bound to these sources")
    if review.get("profile", "pipe-matched-ci-v1") != os.environ.get(
        "MATCHED_PROFILE", "pipe-matched-ci-v1"
    ):
        raise RuntimeError("NoParityClaim: allocation does not authorize this profile")
    if (HERE / "CLI-ASSOCIATION-PENDING.json").exists() and review.get(
        "cli_identity_qualified"
    ) is not True:
        raise RuntimeError("NoParityClaim: prospective CLI correction is not qualified")
    verify_sourcepins()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "admit"])
    args = parser.parse_args()
    if args.action == "admit":
        admit()
    else:
        json.dump(static_check(), sys.stdout, indent=2)
        print()
