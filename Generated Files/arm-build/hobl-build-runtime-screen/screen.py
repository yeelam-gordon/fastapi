"""One same-allocation, build-only runtime control; no retries."""

import argparse
import ctypes
import dataclasses
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import sysconfig
import urllib.request

HERE = Path(__file__).absolute().parent
COMMON = HERE.with_name("hobl-complete-ci")
PARALLEL = HERE.with_name("hobl-parallel-screen")
sys.path[:0] = [str(PARALLEL), str(COMMON)]
from screen import digest, git, load, phase, prepare_source, save, source_snapshot
from native import native_machine
from owned_process import run_owned
from prepare_uv import attest
from artifact_gate import artifact_set, equivalent

GUARD_SHA = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
WHEEL = "pdm_backend-2.5.0-py3-none-any.whl"
WHEEL_SHA = "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63"


def schedule():
    return [("stock", False), ("managed", False),
            ("stock", True), ("managed", True),
            ("managed", True), ("stock", True)]


def command(uv, python, output):
    return [str(uv), "build", "--python", str(python),
            "--no-python-downloads", "--default-index", "https://pypi.org/simple",
            "--build-constraints", str(output / "build-constraints.txt"),
            "--offline", "--no-index", "--find-links", str(output / "wheels")]


def identity():
    process, native = ctypes.c_ushort(), ctypes.c_ushort()
    kernel = ctypes.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    assert kernel.IsWow64Process2(ctypes.c_void_p(kernel.GetCurrentProcess()), ctypes.byref(process),
                                 ctypes.byref(native))
    assert process.value == 0 and native.value == 0xAA64
    assert sys.version_info[:3] == (3, 13, 15)
    assert sysconfig.get_platform() == "win-arm64"
    assert sys._is_gil_enabled() and not sysconfig.get_config_var("Py_GIL_DISABLED")
    assert not hasattr(sys, "gettotalrefcount") and not sysconfig.get_config_var("Py_DEBUG")
    return dict(executable=sys.executable, version=sys.version,
                native=native_machine(Path(sys.executable)),
                machine=platform.machine(), cpu_count=os.cpu_count(),
                processor=platform.processor(), platform=platform.platform(),
                normal_gil=True, debug=False, process_machine=process.value,
                host_machine=native.value)


def environment(output):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("PYTHON", "PYTEST", "PIP_", "UV_", "COVERAGE", "COV_CORE")):
            del env[key]
    env.update(UV_CACHE_DIR=str(output / "build-cache"), UV_HTTP_RETRIES="0",
               UV_PYTHON_DOWNLOADS="never", PYTHONDONTWRITEBYTECODE="1")
    return env


def prepare(args):
    if args.supplied_wheel is None:
        prepare_source(args.source)
    canonical = source_snapshot(args.source)
    save(args.output / "source-before.json", canonical)
    save(args.output / "source-proof.json", {
        "revision": git(args.source, "rev-parse", "HEAD").decode().strip(),
        "files": len(canonical), "manifest_sha256": digest(PARALLEL / "source-manifest.json"),
        "git_modes": git(args.source, "ls-files", "--stage").decode().splitlines(),
        "added_mode": {"conftest.py": "100644"}})
    shutil.copyfile(COMMON / "build-constraints.txt", args.output / "build-constraints.txt")
    save(args.output / "uv-identity.json", attest(args.uv))
    wheels = args.output / "wheels"
    wheels.mkdir()
    if args.supplied_wheel is not None:
        assert args.supplied_wheel.name == WHEEL
        assert digest(args.supplied_wheel) == WHEEL_SHA
        shutil.copyfile(args.supplied_wheel, wheels / WHEEL)
        assert digest(wheels / WHEEL) == WHEEL_SHA
        save(args.output / "wheel-provenance.json", {
            "filename": WHEEL, "sha256": WHEEL_SHA,
            "supplied_wheel": str(args.supplied_wheel),
            "scope": "Explicit local preflight input only; canonical patched source verified; no network fallback"})
        return
    with urllib.request.urlopen("https://pypi.org/pypi/pdm-backend/2.5.0/json",
                                timeout=15) as response:
        metadata = json.load(response)
    entry, = [entry for entry in metadata["urls"] if entry["filename"] == WHEEL]
    assert entry["digests"]["sha256"] == WHEEL_SHA
    with urllib.request.urlopen(entry["url"], timeout=20) as response:
        (wheels / WHEEL).write_bytes(response.read())
    assert digest(wheels / WHEEL) == WHEEL_SHA
    save(args.output / "wheel-provenance.json", entry)


def worker(args):
    env = environment(args.output)
    for arm in ("stock", "managed"):
        phase([str(getattr(args, arm)), "-I", "-B", str(HERE / "screen.py"),
               "identity"], args.source, env, args.output, f"{arm}-identity", 10)
        save(args.output / f"{arm}-identity.json",
             load(args.output / f"{arm}-identity.stdout"))
    canonical = source_snapshot(args.source)
    baseline, rows = None, []
    save(args.output / "protocol.json", {
        "schedule": schedule(), "owned_cap_seconds": 75,
        "commands": {arm: command(args.uv, getattr(args, arm), args.output)
                     for arm in ("stock", "managed")},
        "environment": {k: v for k, v in env.items() if k.startswith(("UV_", "PYTHON"))},
        "clock": "existing phase perf_counter_ns around complete uv process"})
    for index, (arm, measured) in enumerate(schedule()[:2] if args.smoke else schedule(), 1):
        folder = args.output / f"build-{index:02}-{arm}"
        folder.mkdir()
        dist = args.source / "dist"
        if dist.exists():
            shutil.rmtree(dist)
        timing = phase(command(args.uv, getattr(args, arm), args.output),
                       args.source, env, folder, "build", 20)
        shutil.move(str(dist), str(folder / "artifacts"))
        archives = artifact_set(folder / "artifacts", args.source, canonical)
        if baseline is not None:
            equivalent(archives, baseline)
        else:
            baseline = archives
        save(folder / "archive-proof.json", archives)
        rows.append(dict(index=index, arm=arm, measured=measured, **timing))
        save(args.output / "rows.json", rows)
    assert source_snapshot(args.source) == canonical
    save(args.output / "source-after.json", canonical)
    if args.smoke:
        return
    medians = {arm: statistics.median(row["seconds"] for row in rows
               if row["arm"] == arm and row["measured"]) for arm in ("stock", "managed")}
    pairs = [dict(order="AB", stock=rows[2]["seconds"], managed=rows[3]["seconds"]),
             dict(order="BA", stock=rows[5]["seconds"], managed=rows[4]["seconds"])]
    for pair in pairs:
        pair["delta_seconds"] = pair["stock"] - pair["managed"]
        pair["relative_improvement"] = pair["delta_seconds"] / pair["stock"]
    delta = medians["stock"] - medians["managed"]
    relative = delta / medians["stock"]
    save(args.output / "result.json", dict(
        status="PENDING_NATURAL_DRAIN", medians=medians, delta_seconds=delta,
        relative_improvement=relative, pairs=pairs, quality_all=True,
        advance=relative >= .05 and delta >= .2 and all(p["delta_seconds"] > 0 for p in pairs)))


def main(args):
    if args.action == "identity":
        print(json.dumps(identity()))
        return
    for key in ("source", "output", "uv", "stock", "managed"):
        setattr(args, key, getattr(args, key).absolute())
    assert digest(COMMON / "owned_process.py") == GUARD_SHA
    if args.action == "prepare":
        prepare(args)
    elif args.action == "worker":
        worker(args)
    else:
        argv = [str(args.stock), "-I", "-B", str(HERE / "screen.py"), "worker"]
        for key in ("source", "output", "uv", "stock", "managed"):
            argv += ["--" + key, str(getattr(args, key))]
        if args.smoke:
            argv += ["--smoke"]
        receipt = run_owned(argv, cwd=str(args.source), env=environment(args.output),
                            stdout_path=args.output / "driver.stdout",
                            stderr_path=args.output / "driver.stderr", timeout=75,
                            native_clock=True)
        save(args.output / "ownership.json", dataclasses.asdict(receipt))
        assert receipt.succeeded, "Strict ownership failed; retain first failure; no waiver"
        if not args.smoke:
            result = load(args.output / "result.json")
            result["status"] = "COMPLETE_BUILD_ONLY_CONTROL"
            save(args.output / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run", "worker", "identity"])
    for key in ("source", "output", "uv", "stock", "managed"):
        parser.add_argument("--" + key, type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--supplied-wheel", type=Path)
    main(parser.parse_args())
