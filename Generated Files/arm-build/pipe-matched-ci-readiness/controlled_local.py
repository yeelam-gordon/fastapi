"""Explicit local83 pipe/control pairing, never CI admission or token treatment."""

import argparse
import ctypes
import importlib.metadata
import json
import os
import shutil
import sys
import time
from pathlib import Path

import execution as base
from build_readiness import copy_uv_archives
from local_preflight import local_metadata
from matched import HERE, command_plan
from screen import COMMON, digest, load, save
from source_prepare import fresh_payload, owned_helpers

PROFILE = "pipe-fixed-groups-local83-v1"
CONTROL = "1f6a3a788adc3594f2c5666c689c4f8b901df5a5b04c8df8de7526757cdb7fea"
UV = "ec27977d62b5f6091bce410a8e69d40d07541803314e0120905c0ad0affaa5cc"


def sources():
    plan = load(HERE / "CONTROLLED-PENDING.json")
    root = HERE.parents[2]
    for name, sha in plan["source_sha256"].items():
        if digest(root / name) != sha:
            raise ValueError(f"Controlled profile source changed: {name}")


def control():
    if (
        digest(HERE / "fixed_worker.py") != CONTROL
        or importlib.metadata.version("pytest-xdist") != "3.8.0"
    ):
        raise ValueError("Wrong fixed control hash/xdist version")
    import fixed_worker

    for module in (fixed_worker.loadgroup, fixed_worker.loadscope):
        if digest(Path(module.__file__)) != fixed_worker.SOURCE_HASHES[module.__name__]:
            raise ValueError("Pinned scheduler source changed")
    return fixed_worker


def dispatch(folder, cases):
    module = control()
    plan = load(folder / "fixed-worker-plan.json")
    workers = [f"gw{i}" for i in range(4)]
    raw = load(folder / "collection-gw0.json")
    if (
        len(raw) != cases
        or len(set(raw)) != cases
        or any(load(folder / f"collection-{worker}.json") != raw for worker in workers)
    ):
        raise ValueError("Incomplete controlled collection")

    def split(node):
        return module.FixedLoadGroup._split_scope(None, node)

    owners = module.group_plan(raw, workers, split, True)
    sent = {
        worker: [
            node
            for scope, owner in owners.items()
            if owner == worker
            for node in raw
            if split(node) == scope
        ]
        for worker in workers
    }
    starts = {
        worker: [
            json.loads(line)["nodeid"]
            for line in (folder / f"phases-{worker}.jsonl").read_text().splitlines()
            if json.loads(line)["when"] == "setup"
        ]
        for worker in workers
    }
    if (
        plan["status"] != "EXACT_DISPATCH"
        or plan["exitstatus"] != 0
        or plan["collected_cases"] != cases
        or plan["scheduled_cases"] != cases
        or plan["source_hashes"] != module.SOURCE_HASHES
        or plan["group_owners"] != owners
        or plan["sent_by_worker"] != sent
        or starts != sent
    ):
        raise ValueError("Controlled whole-group dispatch/order mismatch")
    return {
        "group_owners": owners,
        "sent_by_worker": sent,
        "source_hashes": module.SOURCE_HASHES,
    }


def dispatch_inputs(folder):
    required = {"fixed-worker-plan.json"} | {
        f"{prefix}-gw{index}.{suffix}"
        for index in range(4)
        for prefix, suffix in (("collection", "json"), ("phases", "jsonl"))
    }
    paths = {
        path.name: path
        for pattern in ("collection-*.json", "phases-*.jsonl", "fixed-worker-plan.json")
        for path in folder.glob(pattern)
        if path.is_file()
    }
    if not required <= paths.keys() or paths.keys() - required - {
        "phases-controller.jsonl"
    }:
        raise ValueError("Controlled readiness evidence inventory differs")
    return {name: digest(path) for name, path in sorted(paths.items())}


def affinity():
    if sys.platform != "win32":
        raise ValueError("This explicit local83 profile is Windows only")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.restype = ctypes.c_void_p
    api.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    api.SetProcessAffinityMask.restype = ctypes.c_int
    api.GetProcessAffinityMask.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    api.GetProcessAffinityMask.restype = ctypes.c_int
    process, system = ctypes.c_size_t(), ctypes.c_size_t()
    handle = api.GetCurrentProcess()
    if (
        not api.SetProcessAffinityMask(handle, 15)
        or not api.GetProcessAffinityMask(
            handle, ctypes.byref(process), ctypes.byref(system)
        )
        or process.value != 15
    ):
        raise RuntimeError("Owned four-LP mask unavailable")


def readiness(args):
    metadata = local_metadata()
    control()
    affinity()
    import _pytest.assertion.rewrite as rewrite

    ready = {
        "accepted": True,
        "mac_runtime_accepted": False,
        "profile": PROFILE,
        "local83": metadata,
        "rewrite_pin": {
            "path": rewrite.__file__,
            "sha256": digest(Path(rewrite.__file__)),
        },
    }
    save(args.output / "readiness.json", ready)
    return ready


def commands(python, uv, source, output, workers):
    value = command_plan(python, uv, source, output, workers)
    value["test"] += ["-p", "fixed_worker"]
    return value


def child_command(args, action):
    command = [
        sys.executable,
        "-B",
        str(Path(__file__)),
        action,
        "--source",
        str(args.source),
        "--output",
        str(args.output),
        "--uv",
        str(args.uv),
        "--wheel-dir",
        str(args.wheel_dir),
    ]
    return command + (
        ["--control-ready", str(args.control_ready)] if args.control_ready else []
    )


def run_worker(args):
    started = time.monotonic()
    if args.control_ready is None:
        raise ValueError("A retained four-group readiness proof is required")
    gate = load(args.control_ready / "controlled-readiness.json")
    if gate["pending_sha256"] != digest(HERE / "CONTROLLED-PENDING.json") or gate[
        "receipt_sha256"
    ] != digest(args.control_ready / "four-group-control-receipt.json"):
        raise ValueError("Four-group readiness is not source/receipt bound")
    receipt = load(args.control_ready / "four-group-control-receipt.json")
    if (
        receipt["returncode"] != 0
        or receipt["timed_out"]
        or receipt["survivors"] is not False
        or not receipt["ownership_established"]
        or not receipt["cleanup_complete"]
        or receipt["errors"]
    ):
        raise ValueError("Four-group readiness did not naturally drain")
    if (
        gate.get("runtime_preserved") is not True
        or gate.get("evidence_sha256") != dispatch_inputs(args.control_ready)
        or gate["dispatch"] != dispatch(args.control_ready, 4)
    ):
        raise ValueError("Four-group readiness objective/evidence changed")
    readiness(args)
    wheel = args.wheel_dir / "pdm_backend-2.5.0-py3-none-any.whl"
    if digest(args.uv) != UV or digest(wheel) != base.BACKEND_SHA:
        raise ValueError("Exact qualified uv/nested PDM wheel required")
    (args.output / "wheels").mkdir()
    shutil.copyfile(wheel, args.output / "wheels" / wheel.name)
    shutil.copyfile(
        COMMON / "build-constraints.txt", args.output / "build-constraints.txt"
    )
    shutil.copyfile(HERE / "full-coverage.toml", args.output / "full-coverage.toml")
    rows = []
    for index, arm in enumerate(("A", "B", "B", "A"), 1):
        folder, source = (
            args.output / f"payload-{index:02}-{arm}",
            args.output / f"source-{index:02}-{arm}",
        )
        folder.mkdir()
        manifest = fresh_payload(args.source, source)
        helper = folder / "owned-helpers"
        owned_helpers(helper)
        save(folder / "source-before.json", manifest)
        rows.append(
            {
                "index": index,
                "arm": arm,
                "profile": PROFILE,
                "folder": str(folder),
                "source": str(source),
                "manifest": str(folder / "source-before.json"),
                "helper": str(helper),
                "helper_sources": {
                    path.name: digest(path) for path in helper.iterdir()
                },
            }
        )
    save(args.output / "payloads.json", rows)
    args.seconds = 385 - (time.monotonic() - started)
    if args.seconds <= 120:
        raise TimeoutError("No payload allocation remains")
    base.worker(
        args,
        readiness_check=readiness,
        commands=commands,
        audit_commands=child_command,
        archive_copy=copy_uv_archives,
    )


def small_readiness(args):
    before = base.runtime_snapshot(Path(sys.prefix))
    try:
        readiness(args)
        fixture = args.output / "four-groups"
        fixture.mkdir()
        (fixture / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        for group in range(4):
            (fixture / f"test_group{group}.py").write_text(
                "def test_dispatch():\n    assert True\n", encoding="utf-8"
            )
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PYTHON", "PYTEST", "COVERAGE", "COV_CORE"))
        }
        env.update(
            PYTHONPATH=str(HERE),
            CORRECTNESS_OUTPUT=str(args.output),
            CORRECTNESS_SOURCE=str(fixture),
            CHECK_COVERAGE="0",
            CHECK_FIXTURE="0",
            FULL_SUITE="0",
        )
        base.owned(
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "-c",
                str(fixture / "pytest.ini"),
                str(fixture),
                "-q",
                "-n",
                "4",
                "--dist=loadgroup",
                "--max-worker-restart=0",
                "-p",
                "fixed_worker",
                "-p",
                "resource_observer",
                "-p",
                "no:cacheprovider",
                f"--basetemp={args.output / 'pytest-owned'}",
            ],
            fixture,
            env,
            args.output,
            "four-group-control",
            60,
        )
        objective = dispatch(args.output, 4)
        evidence = dispatch_inputs(args.output)
    finally:
        if base.runtime_snapshot(Path(sys.prefix)) != before:
            raise ValueError(
                "Original runtime/cache changed during controlled readiness"
            )
    save(
        args.output / "controlled-readiness.json",
        {
            "dispatch": objective,
            "evidence_sha256": evidence,
            "runtime_preserved": True,
            "pending_sha256": digest(HERE / "CONTROLLED-PENDING.json"),
            "receipt_sha256": digest(args.output / "four-group-control-receipt.json"),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["readiness", "run", "worker", "cheap", "first-pair", "final"]
    )
    parser.add_argument("--source", type=Path, default=HERE.parents[5])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--uv", type=Path, default=HERE.parents[4] / "arm-build" / "tools" / "uv.exe"
    )
    parser.add_argument(
        "--wheel-dir",
        type=Path,
        default=HERE.parents[4] / "arm-build" / "wheelhouse" / "ci-40814042898",
    )
    parser.add_argument("--control-ready", type=Path)
    args = parser.parse_args()
    args.workers = 4
    for name in ("source", "output", "uv", "wheel_dir"):
        setattr(args, name, getattr(args, name).resolve())
    if args.control_ready is not None:
        args.control_ready = args.control_ready.resolve()
    sources()
    if not args.output.is_relative_to(
        HERE.parents[4] / "arm-build" / "pipe-matched-ci-readiness"
    ):
        raise ValueError("New owned outputs only")
    if args.action in ("readiness", "run"):
        args.output.mkdir(exist_ok=False)
        affinity()
        if args.action == "readiness":
            small_readiness(args)
        else:
            base.owned(
                child_command(args, "worker"),
                HERE,
                os.environ.copy(),
                args.output,
                "controlled-owner",
                420,
            )
    elif args.action == "worker":
        run_worker(args)
    else:
        rows = load(args.output / "audit-rows.json")
        proofs = [dispatch(Path(row["folder"]), 2643) for row in rows]
        if any(value != proofs[0] for value in proofs):
            raise ValueError("Controlled dispatch differs across retained payloads")
        if args.action == "cheap":
            save(Path(rows[0]["folder"]) / "controlled-dispatch-proof.json", proofs[0])
        base.audit(args)
