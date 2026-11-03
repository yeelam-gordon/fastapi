"""One bounded prospective screen; no local cohort or automatic retry."""

import argparse
import dataclasses
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import sysconfig
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from native import native_machine

HERE = Path(__file__).absolute().parent
COMMON = HERE.with_name("hobl-complete-ci")
sys.path.insert(0, str(COMMON))
from owned_process import run_owned  # noqa: E402
from prepare_uv import attest  # noqa: E402
from runtime_pair import SOURCE_REVISION, corrected, normalize  # noqa: E402


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schedule():
    return [
        ("serial", False),
        ("parallel", False),
        ("serial", True),
        ("parallel", True),
        ("parallel", True),
        ("serial", True),
    ]


def phase(command, source, env, folder, name, timeout):
    with (
        (folder / f"{name}.stdout").open("wb") as out,
        (folder / f"{name}.stderr").open("wb") as err,
    ):
        start = time.perf_counter_ns()
        try:
            result = subprocess.run(
                command,
                cwd=source,
                env=env,
                stdout=out,
                stderr=err,
                timeout=timeout,
            )
        finally:
            end = time.perf_counter_ns()
    row = {
        "command": command,
        "start_ns": start,
        "stop_ns": end,
        "seconds": (end - start) / 1e9,
        "exitcode": result.returncode,
    }
    save(folder / f"{name}.json", row)
    assert result.returncode == 0, f"{name} failed: {result.returncode}"
    return row


def git(source, *args):
    return subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout


def source_snapshot(source):
    expected = load(HERE / "source-manifest.json")
    assert len(expected) == 2558
    actual = {name: digest(source / name) for name in expected}
    mismatches = [name for name in expected if actual[name] != expected[name]]
    assert not mismatches, (
        f"Exact Git-source mismatch ({len(mismatches)} files): {mismatches[:10]}"
    )
    return actual


def prepare_source(source):
    assert git(source, "rev-parse", "HEAD").decode().strip() == SOURCE_REVISION
    assert not git(source, "status", "--porcelain")
    (source / "tests" / "utils.py").write_bytes(
        corrected((source / "tests" / "utils.py").read_bytes())
    )
    subprocess.run(
        ["git", "-C", str(source), "apply", str(HERE / "resource-owner.patch")],
        check=True,
        timeout=30,
    )


def prepare(args):
    source, output = args.source, args.output
    save(
        output / "preparation.json", {"status": "started", "revision": SOURCE_REVISION}
    )
    prepare_source(source)
    save(output / "source-before.json", source_snapshot(source))
    save(
        output / "source-proof.json",
        {
            "revision": SOURCE_REVISION,
            "files": 2558,
            "manifest_sha256": digest(HERE / "source-manifest.json"),
            "git_modes": git(source, "ls-files", "--stage").decode().splitlines(),
            "added_mode": {"conftest.py": "100644"},
            "changes": [
                "tests/utils.py guard",
                "two custom docs temp-cwd fixtures",
                "root standard xdist groups",
            ],
        },
    )
    shutil.copyfile(HERE / "full-coverage.toml", output / "full-coverage.toml")
    shutil.copyfile(COMMON / "build-constraints.txt", output / "build-constraints.txt")
    save(output / "uv-identity.json", attest(args.uv))
    native_machine(Path(sys.executable))
    assert sys.version_info[:3] == (3, 13, 15)
    assert os.cpu_count() == args.workers, "Actual host CPU count differs"
    venv = output / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=30)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    wheels = output / "wheels"
    wheels.mkdir()
    env = os.environ.copy()
    env.update(
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_CONSTRAINT=(output / "build-constraints.txt").as_uri(),
    )
    phase(
        [
            str(python),
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--no-deps",
            "--retries",
            "0",
            "--timeout",
            "30",
            "--index-url",
            "https://pypi.org/simple",
            "-d",
            str(wheels),
            "-r",
            str(HERE / "requirements.txt"),
        ],
        source,
        env,
        output,
        "download",
        150,
    )
    locked, provenance = [], []
    for wheel in sorted(wheels.iterdir()):
        name, version = wheel.name.split("-")[:2]
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/{version}/json", timeout=15
        ) as response:
            metadata = json.load(response)
        expected = [
            entry["digests"]["sha256"]
            for entry in metadata["urls"]
            if entry["filename"] == wheel.name
        ]
        assert expected == [digest(wheel)], f"PyPI wheel hash: {wheel.name}"
        locked.append(f"{name}=={version} --hash=sha256:{expected[0]}")
        provenance.append({"filename": wheel.name, "sha256": expected[0]})
    assert len(locked) == 82
    # Both distributions claim ujson-stubs; preserve the tested same-pin last owner.
    locked.sort(key=lambda line: line.startswith("ujson=="))
    lock = output / "installed-hashes.txt"
    lock.write_text("\n".join(locked) + "\n", encoding="utf-8")
    save(output / "wheel-provenance.json", provenance)
    phase(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--require-hashes",
            "--find-links",
            str(wheels),
            "-r",
            str(lock),
        ],
        source,
        env,
        output,
        "install",
        90,
    )
    ujson = next(line for line in locked if line.startswith("ujson=="))
    last = output / "ujson-last.txt"
    last.write_text(ujson + "\n", encoding="utf-8")
    phase(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--force-reinstall",
            "--require-hashes",
            "--find-links",
            str(wheels),
            "-r",
            str(last),
        ],
        source,
        env,
        output,
        "ujson-last",
        30,
    )
    save(
        output / "preparation.json", {"status": "complete", "revision": SOURCE_REVISION}
    )


def identity(args):
    import coverage.tracer
    from packaging.tags import parse_tag, sys_tags

    assert sys.version_info[:3] == (3, 13, 15)
    assert not sysconfig.get_config_var("Py_GIL_DISABLED")
    assert getattr(sys, "_is_gil_enabled", lambda: True)()
    assert not sysconfig.get_config_var("PYTHON_JIT")
    assert not getattr(getattr(sys, "_jit", None), "is_enabled", lambda: False)()
    assert os.cpu_count() == args.workers
    expected = dict(
        line.split("==")
        for line in (HERE / "requirements.txt").read_text().splitlines()
    )
    packages, tags = {}, {}
    compatible = set(sys_tags())
    for dist in importlib.metadata.distributions():
        name = normalize(dist.metadata["Name"])
        packages[name] = dist.version
        wheel = dist.read_text("WHEEL")
        assert wheel, f"Installed wheel metadata missing: {name}"
        values = [line[5:] for line in wheel.splitlines() if line.startswith("Tag: ")]
        assert any(parse_tag(value) & compatible for value in values)
        tags[name] = values
    assert packages == {normalize(k): v for k, v in expected.items()}
    return {
        "python": sys.version,
        "executable": sys.executable,
        "machine": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "os": platform.platform(),
        "normal_gil": True,
        "jit": False,
        "python_native": native_machine(Path(sys.executable)),
        "coverage_native": native_machine(Path(coverage.tracer.__file__)),
        "packages": packages,
        "wheel_tags": tags,
        "ujson_overlap": "same-pin ujson installed last; not all RECORD claims hold",
    }


def tiny_outcome(folder):
    cases = list(ET.parse(folder / "junit.xml").getroot().iter("testcase"))
    counts = {
        "cases": len(cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
        "failures": sum(case.find("failure") is not None for case in cases),
    }
    counts["passed"] = counts["cases"] - sum(
        counts[key] for key in ("skipped", "errors", "failures")
    )
    assert counts == {
        "cases": 2643,
        "passed": 2513,
        "skipped": 130,
        "errors": 0,
        "failures": 0,
    }, counts
    return counts


def test_command(args, folder, arm):
    return [
        sys.executable,
        str(HERE / "bootstrap.py"),
        "run",
        "--rcfile",
        str(args.output / "full-coverage.toml"),
        "-m",
        "pytest",
        "tests",
        "-q",
        "-rA",
        "-p",
        "no:pytest_cov",
        "-p",
        "resource_observer",
        f"--basetemp={folder / 'pytest-owned'}",
        f"--junitxml={folder / 'junit.xml'}",
        "-n",
        str(args.workers if arm == "parallel" else 0),
        *(["--dist=loadgroup", "--max-worker-restart=0"] if arm == "parallel" else []),
    ]


def worker(args):
    source, output = args.source, args.output
    save(output / "native-identity.json", identity(args))
    rows = []
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(
            ("PYTHON", "PYTEST_", "PIP_", "UV_", "COVERAGE_", "COV_CORE_")
        ):
            env.pop(key)
    env.update(
        PYTHONPATH=os.pathsep.join(map(str, [HERE, source, source / "docs_src"])),
        PYTHONIOENCODING="utf-8",
        CONTEXT="",
        PIP_INDEX_URL="https://pypi.org/simple",
        PIP_CONSTRAINT=(output / "build-constraints.txt").as_uri(),
        UV_CACHE_DIR=str(output / "uv-cache"),
        CORRECTNESS_SOURCE=str(source),
        CHECK_COVERAGE="1",
        CHECK_FIXTURE="1",
        FULL_SUITE="1",
    )
    save(
        output / "protocol.json",
        {
            "status": "SCREEN_NOT_ADOPTION",
            "schedule": schedule(),
            "workers": args.workers,
            "runtime_pins": 82,
            "config_sha256": digest(output / "full-coverage.toml"),
            "constraint_uri": env["PIP_CONSTRAINT"],
            "final_audit_budget_seconds": 60,
            "source_hash_scope": "once before/after cohort",
            "archive_coverage_scope": "only final measured BA pair after all timings",
        },
    )
    for index, (arm, measured) in enumerate(schedule(), 1):
        folder = output / f"payload-{index:02}-{arm}"
        folder.mkdir()
        (folder / "temp").mkdir()
        env.update(
            CORRECTNESS_OUTPUT=str(folder),
            COVERAGE_FILE=str(folder / ".coverage"),
            TEMP=str(folder / "temp"),
            TMP=str(folder / "temp"),
            TMPDIR=str(folder / "temp"),
        )
        dist = source / "dist"
        if dist.exists():
            shutil.rmtree(dist)
        start = time.perf_counter_ns()
        build = phase(
            [
                str(args.uv),
                "build",
                "--python",
                sys.executable,
                "--no-python-downloads",
                "--default-index",
                "https://pypi.org/simple",
                "--build-constraints",
                str(output / "build-constraints.txt"),
            ],
            source,
            env,
            folder,
            "build",
            180,
        )
        test = phase(test_command(args, folder, arm), source, env, folder, "test", 240)
        end = time.perf_counter_ns()
        shutil.move(str(dist), str(folder / "artifacts"))
        row = {
            "index": index,
            "arm": arm,
            "measured": measured,
            "build_seconds": build["seconds"],
            "test_seconds": test["seconds"],
            "complete_seconds": (end - start) / 1e9,
            "counts": tiny_outcome(folder),
        }
        rows.append(row)
        save(output / "rows.json", rows)
        print(json.dumps(row), flush=True)
    save(output / "source-after.json", source_snapshot(source))
    summary = {
        arm: {
            metric: statistics.median(
                row[metric] for row in rows if row["measured"] and row["arm"] == arm
            )
            for metric in ("build_seconds", "test_seconds", "complete_seconds")
        }
        for arm in ("serial", "parallel")
    }
    save(
        output / "result.json",
        {
            "status": "SCREEN_PENDING_NATURAL_DRAIN",
            "measured_pairs": 2,
            "medians": summary,
            "relative_improvement": 1
            - summary["parallel"]["complete_seconds"]
            / summary["serial"]["complete_seconds"],
            "pair_savings_seconds": [
                rows[2]["complete_seconds"] - rows[3]["complete_seconds"],
                rows[5]["complete_seconds"] - rows[4]["complete_seconds"],
            ],
        },
    )
    try:
        phase(
            [
                sys.executable,
                str(HERE / "audit.py"),
                str(source),
                str(output),
                str(args.workers),
            ],
            source,
            env,
            output,
            "final-audit",
            60,
        )
    except (subprocess.TimeoutExpired, AssertionError) as error:
        save(
            output / "audit-limit.json",
            {
                "status": "SCREEN_VALIDATION_LIMIT",
                "reason": str(error),
                "automatic_retry": False,
            },
        )


def main(args):
    args.source = args.source.absolute()
    args.output = args.output.absolute()
    args.uv = args.uv.absolute()
    if args.action == "prepare":
        prepare(args)
    elif args.action == "worker":
        worker(args)
    else:
        assert digest(COMMON / "owned_process.py") == (
            "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
        )
        command = [
            sys.executable,
            "-B",
            str(HERE / "screen.py"),
            "worker",
            "--source",
            str(args.source),
            "--output",
            str(args.output),
            "--uv",
            str(args.uv),
            "--workers",
            str(args.workers),
        ]
        receipt = run_owned(
            command,
            cwd=str(args.source),
            env=os.environ.copy(),
            stdout_path=args.output / "driver.stdout",
            stderr_path=args.output / "driver.stderr",
            timeout=720,
        )
        save(args.output / "ownership.json", dataclasses.asdict(receipt))
        assert receipt.succeeded, "Original guardian natural drain failed; no waiver"
        result = load(args.output / "result.json")
        result["status"] = (
            "SCREEN_VALIDATION_LIMIT"
            if (args.output / "audit-limit.json").exists()
            else "SCREEN_COMPLETE_NOT_ADOPTION"
        )
        save(args.output / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run", "worker"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=[3, 4], required=True)
    main(parser.parse_args())
