"""Finite matched ABBA runner using the existing qualified ownership guardian."""

import argparse
import dataclasses
import importlib.util
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

from matched import HERE, command_plan
from screen import COMMON, digest, identity, load, save

sys.path.insert(0, str(COMMON))
from owned_process import run_owned

GUARD_SHA = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
BACKEND_SHA = "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63"


def remaining(deadline, reserve=0, cap=120):
    value = min(cap, deadline - time.monotonic() - reserve)
    if value <= 1:
        raise TimeoutError("Remaining allocation exhausted; no command admitted")
    return value


def owned(command, cwd, env, folder, name, timeout, native=False):
    if digest(COMMON / "owned_process.py") != GUARD_SHA:
        raise ValueError("Qualified ownership guardian bytes changed")
    if timeout <= 16:
        raise TimeoutError("Insufficient command plus guardian cleanup budget")
    receipt = run_owned(
        list(map(str, command)),
        cwd=str(cwd),
        env=env,
        stdout_path=folder / f"{name}.stdout",
        stderr_path=folder / f"{name}.stderr",
        timeout=timeout - 15,
        native_clock=native,
    )
    save(folder / f"{name}-receipt.json", dataclasses.asdict(receipt))
    if not receipt.succeeded:
        if (receipt.returncode == 2 or name == "test" and receipt.returncode == 1) and (
            not receipt.timed_out
            and receipt.ownership_established
            and receipt.survivors is False
            and receipt.cleanup_complete
            and not receipt.errors
        ):
            raise ValueError(f"{name}: command validation failed; no retry")
        raise RuntimeError(
            f"{name}: failed/timeout/ownership/cleanup receipt; no retry"
        )
    return receipt


def runtime_snapshot(root):
    return {
        str(path.relative_to(root)): digest(path)
        for path in root.rglob("*")
        if path.is_file()
    }


def runtime_preserved(root, before):
    for name, sha in before.items():
        if digest(root / name) != sha:
            raise ValueError(f"Original runtime/cache input changed: {name}")
    for path in root.rglob("*"):
        if path.is_file() and str(path.relative_to(root)) not in before:
            if path.suffix != ".pyc" or "__pycache__" not in path.parts:
                raise ValueError(f"Undeclared generated runtime output: {path}")
            source = path.parent.parent / (path.name.split(".")[0] + ".py")
            if str(source.relative_to(root)) not in before:
                raise ValueError("Generated dependency pyc has no immutable source")


def prepare(args):
    """Reuse the existing common82 bootstrap verbatim, not a new installer."""
    from screen import prepare as common_prepare
    from source_prepare import fresh_payload, owned_helpers

    if (args.output / "venv").exists():
        raise ValueError("Preparation requires a new owned runtime")
    args.output.mkdir(exist_ok=True)
    bootstrap_source = args.output / "bootstrap-source"
    # Bootstrap requires the original five changes, not the ExitStack overlay.
    from screen import git

    git(
        args.source,
        "worktree",
        "add",
        "--detach",
        str(bootstrap_source),
        "864b569cf8453654fc3bc2c64108c0f644e2918c",
    )
    common_prepare(
        SimpleNamespace(
            source=bootstrap_source,
            output=args.output,
            uv=args.uv,
            workers=args.workers,
        )
    )
    wheels = args.output / "wheels"
    backend = list(wheels.glob("pdm_backend-2.5.0-*.whl"))
    if len(backend) != 1 or digest(backend[0]) != BACKEND_SHA:
        raise ValueError("Existing qualified backend wheel/publisher pin differs")
    # Source preparation is outside clocks; every measured payload is fresh.
    rows = []
    for index, arm in enumerate(("A", "B", "B", "A"), 1):
        folder = args.output / f"payload-{index:02}-{arm}"
        folder.mkdir()
        source = args.output / f"source-{index:02}-{arm}"
        manifest = fresh_payload(args.source, source)
        helper = folder / "owned-helpers"
        owned_helpers(helper)
        path = folder / "source-before.json"
        save(path, manifest)
        rows.append(
            {
                "index": index,
                "arm": arm,
                "folder": str(folder),
                "source": str(source),
                "manifest": str(path),
                "helper": str(helper),
                "helper_sources": {
                    path.name: digest(path) for path in helper.iterdir()
                },
            }
        )
    save(args.output / "payloads.json", rows)


def readiness(args):
    import zipfile

    import coverage.tracer
    from provenance import mac_runtime, source_contract

    metadata = identity(args)
    source_contract()
    provenance = load(args.output / "wheel-provenance.json")
    for row in provenance:
        if digest(args.output / "wheels" / row["filename"]) != row["sha256"]:
            raise ValueError("Existing common82 platform wheel provenance differs")
    native = Path(coverage.tracer.__file__)
    coverage_wheel = [
        row for row in provenance if row["filename"].startswith("coverage-7.17.0-")
    ]
    if len(coverage_wheel) != 1:
        raise ValueError("Unique pinned platform coverage wheel required")
    with zipfile.ZipFile(
        args.output / "wheels" / coverage_wheel[0]["filename"]
    ) as wheel:
        members = [name for name in wheel.namelist() if Path(name).name == native.name]
        if len(members) != 1 or wheel.read(members[0]) != native.read_bytes():
            raise ValueError(
                "Installed native CTracer differs from hash-locked platform wheel"
            )
    result = {"accepted": True, "mac_runtime_accepted": False, "identity": metadata}
    if sys.platform == "darwin":
        result["mac_runtime_certificate"] = mac_runtime()
        result["mac_runtime_accepted"] = True
    rewrite = Path(importlib.util.find_spec("_pytest.assertion.rewrite").origin)
    result["rewrite_pin"] = {"path": str(rewrite), "sha256": digest(rewrite)}
    save(args.output / "readiness.json", result)
    return result


def environment(args, row):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            ("PYTHON", "PYTEST_", "PIP_", "UV_", "COVERAGE_", "COV_CORE_")
        )
    }
    folder, source = Path(row["folder"]), Path(row["source"])
    temp = folder / "temp"
    temp.mkdir()
    env.update(
        PYTHONPATH=os.pathsep.join(
            map(str, (Path(row["helper"]), source, source / "docs_src"))
        ),
        PYTHONIOENCODING="utf-8",
        OWNER_ARM=row["arm"],
        CORRECTNESS_SOURCE=str(source),
        CORRECTNESS_OUTPUT=str(folder),
        MATCHED_READINESS=str(args.output / "readiness.json"),
        COVERAGE_FILE=str(folder / ".coverage"),
        COVERAGE_RCFILE=str(args.output / "full-coverage.toml"),
        CONTEXT="",
        CHECK_COVERAGE="1",
        CHECK_FIXTURE="1",
        FULL_SUITE="1",
        TEMP=str(temp),
        TMP=str(temp),
        TMPDIR=str(temp),
        UV_CACHE_DIR=str(args.output / "uv-cache"),
        UV_FIND_LINKS=(args.output / "wheels").as_uri(),
        PIP_FIND_LINKS=(args.output / "wheels").as_uri(),
        PIP_NO_INDEX="1",
        PIP_CONSTRAINT=(args.output / "build-constraints.txt").as_uri(),
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        SOURCE_DATE_EPOCH="1700000000",
    )
    return env


def audit_command(args, action):
    return [
        sys.executable,
        "-B",
        str(HERE / "execution.py"),
        action,
        "--source",
        str(args.source),
        "--output",
        str(args.output),
        "--uv",
        str(args.uv),
        "--workers",
        str(args.workers),
    ]


def orchestrate(rows, deadline, phase, cheap_gate, first_pair, final_gate):
    """Single fixed schedule; callbacks permit focused tests without workloads."""
    if [row["arm"] for row in rows] != ["A", "B", "B", "A"]:
        raise ValueError("Exactly four ABBA payloads required")
    measured = []
    for index, row in enumerate(rows):
        value = dict(row)
        for name in ("build", "test"):
            value[name + "_seconds"] = phase(
                row, name, remaining(deadline, reserve=120, cap=180)
            )
        value["total_seconds"] = value["build_seconds"] + value["test_seconds"]
        cheap_gate(value, remaining(deadline, reserve=120, cap=45))
        measured.append(value)
        if index == 1:
            first_pair(measured, remaining(deadline, reserve=120, cap=90))
    final_gate(measured, remaining(deadline, cap=120))
    return measured


def within_host(rows):
    pairs = [(rows[0], rows[1]), (rows[3], rows[2])]
    orders = []
    for stock, candidate in pairs:
        saved = stock["total_seconds"] - candidate["total_seconds"]
        orders.append(
            {
                "saved_seconds": saved,
                "relative_saved": saved / stock["total_seconds"],
                "build_gap": stock["build_seconds"] - candidate["build_seconds"],
                "covered_test_gap": stock["test_seconds"] - candidate["test_seconds"],
                "threshold_met": saved >= 0.5
                and saved / stock["total_seconds"] >= 0.01
                and candidate["test_seconds"] <= stock["test_seconds"],
                "no_covered_test_timing_regression": candidate["test_seconds"]
                <= stock["test_seconds"],
            }
        )
    return {
        "orders": orders,
        "windows_threshold_both_orders": all(row["threshold_met"] for row in orders),
        "parity_claim": False,
    }


def compare(windows, macos):
    for result in (windows, macos):
        if result["status"] != "VALIDATED_NO_PARITY_CLAIM" or len(result["rows"]) != 4:
            raise ValueError("Both complete validated host results required")
    values = []
    for index in (1, 2):
        win, mac = windows["rows"][index], macos["rows"][index]
        values.append(
            {
                metric: win[metric] - mac[metric]
                for metric in ("build_seconds", "test_seconds", "total_seconds")
            }
        )
    return {
        "position_matched_B_gaps_windows_minus_macos": values,
        "primary_timing_threshold_both_orders": all(
            row["total_seconds"] <= 0 for row in values
        ),
        "physical_parity_proven": False,
        "adoption": False,
        "scope": "finite service-host timing only; resource/physical limits remain explicit",
    }


def worker(
    args,
    *,
    readiness_check=None,
    commands=command_plan,
    audit_commands=audit_command,
    archive_copy=None,
):
    deadline = time.monotonic() + args.seconds
    before = runtime_snapshot(Path(sys.prefix))
    result = {"status": "ERROR", "rows": [], "failures": []}
    save(args.output / "runtime-before.json", before)
    try:
        ready = (readiness if readiness_check is None else readiness_check)(args)
        rows = load(args.output / "payloads.json")

        def phase(row, name, budget):
            folder = Path(row["folder"])
            command = commands(
                sys.executable, args.uv, row["source"], args.output, args.workers
            )[name]
            if name == "test":
                command = commands(
                    sys.executable, args.uv, row["source"], folder, args.workers
                )[name]
                command[command.index("--rcfile") + 1] = str(
                    args.output / "full-coverage.toml"
                )
                command[1] = str(Path(row["helper"]) / "bootstrap.py")
            receipt = owned(
                command,
                row["source"],
                environment_for(row),
                folder,
                name,
                budget,
                native=True,
            )
            if receipt.native_start_ns is None or receipt.native_end_ns is None:
                raise ValueError("Native phase clocks absent")
            if name == "build":
                text = (folder / "build.stderr").read_text(encoding="utf-8")
                if (
                    "Building source distribution" not in text
                    or "Building wheel from source distribution" not in text
                ):
                    raise ValueError("Full sdist then wheel-from-sdist not observed")
                if archive_copy is None:
                    shutil.move(
                        str(Path(row["source"]) / "dist"), str(folder / "artifacts")
                    )
                else:
                    archive_copy(Path(row["source"]) / "dist", folder / "artifacts")
            return (receipt.native_end_ns - receipt.native_start_ns) / 1e9

        environments = {}

        def environment_for(row):
            if row["index"] not in environments:
                environments[row["index"]] = environment(args, row)
            return environments[row["index"]]

        def audit_stage(action, measured, budget):
            save(args.output / "audit-rows.json", measured)
            owned(
                audit_commands(args, action),
                HERE,
                os.environ.copy(),
                args.output,
                action + "-" + str(len(measured)),
                budget,
            )

        def cheap_gate(row, budget):
            audit_stage("cheap", [row], budget)
            result["rows"].append(row)
            save(args.output / "result.json", result)

        measured = orchestrate(
            rows,
            deadline,
            phase,
            cheap_gate,
            lambda rows, budget: audit_stage("first-pair", rows, budget),
            lambda rows, budget: audit_stage("final", rows, budget),
        )
        result.update(
            status="VALIDATED_NO_PARITY_CLAIM",
            rows=measured,
            comparison=within_host(measured),
            readiness=ready,
        )
    except ValueError as error:
        result.update(status="VALIDATION_FAILED_NO_PARITY_CLAIM")
        result["failures"].append(repr(error))
        raise
    except BaseException as error:
        result["failures"].append(repr(error))
        raise
    finally:
        try:
            if result["status"] != "VALIDATED_NO_PARITY_CLAIM":
                runtime_preserved(Path(sys.prefix), before)
        except BaseException as error:
            result["status"] = "ERROR"
            result["failures"].append("final preservation: " + repr(error))
            raise
        finally:
            save(args.output / "result.json", result)


def main(args):
    from matched import admit

    admit()
    args.source, args.output, args.uv = (
        args.source.resolve(),
        args.output.resolve(),
        args.uv.resolve(),
    )
    if args.action == "prepare":
        args.output.mkdir(exist_ok=False)
        owned(
            audit_command(args, "prepare-worker"),
            HERE,
            os.environ.copy(),
            args.output,
            "prepare",
            args.seconds,
        )
    elif args.action == "prepare-worker":
        prepare(args)
    elif args.action == "run":
        from matched import admit

        admit()
        command = audit_command(args, "worker") + [
            "--seconds",
            str(max(1, args.seconds - 35)),
        ]
        owned(command, HERE, os.environ.copy(), args.output, "controller", args.seconds)
    elif args.action == "worker":
        worker(args)
    else:
        audit(args)


def audit(args):
    import matched_audit

    rows = load(args.output / "audit-rows.json")
    if args.action == "cheap":
        ready = load(args.output / "readiness.json")
        matched_audit.cheap(rows[0], args.workers, ready["rewrite_pin"])
    elif args.action == "first-pair":
        for row in rows:
            matched_audit.full(row)
        matched_audit.equal_pair(rows[0]["folder"], rows[1]["folder"])
    else:
        proof = matched_audit.final(rows)
        ready = load(args.output / "readiness.json")
        for row in rows:
            cached = load(Path(row["folder"]) / "cheap-proof.json")
            pids = {
                item["pid"]
                for item in cached["identities"]
                if item["worker"] != "controller"
            }
            matched_audit.source_gate(row, pids, ready["rewrite_pin"])
        runtime_preserved(Path(sys.prefix), load(args.output / "runtime-before.json"))
        proof["final_runtime_and_sources_preserved"] = True
        save(args.output / "final-audit.json", proof)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=[
            "prepare",
            "prepare-worker",
            "run",
            "worker",
            "cheap",
            "first-pair",
            "final",
        ],
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=420)
    try:
        main(parser.parse_args())
    except (ValueError, AssertionError):
        traceback.print_exc()
        raise SystemExit(2) from None
    except BaseException:
        traceback.print_exc()
        raise SystemExit(1) from None
