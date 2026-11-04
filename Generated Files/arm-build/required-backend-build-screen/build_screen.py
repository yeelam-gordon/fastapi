"""Finite prepared-project build screen; no dispatch or default execution."""

import argparse
import base64
import csv
import ctypes
import dataclasses
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
COMMON = HERE.with_name("hobl-complete-ci")
PARALLEL = HERE.with_name("hobl-parallel-screen")
sys.path.insert(0, str(PARALLEL))
sys.path.insert(0, str(COMMON))
import screen as parallel  # noqa: E402
from owned_process import run_owned  # noqa: E402

PDM_HASH = "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63"
GUARD_HASH = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
SCHEDULE = ("A", "B", "B", "A")


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def archive_helper():
    path = HERE.with_name("hobl-secure-wipe-screen") / "screen.py"
    spec = importlib.util.spec_from_file_location("build_archive_helpers", path)
    module = importlib.util.module_from_spec(spec)
    before = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


def build_command(context, arm, output):
    argv = [
        context["uv"],
        "--no-config",
        "--offline",
        "--cache-dir",
        context["cache"],
        "build",
        context["source"],
        "--python",
        sys.executable,
        "--no-python-downloads",
        "--no-index",
        "--find-links",
        context["wheels"],
        "--build-constraints",
        context["constraint"],
        "--require-hashes",
        "--out-dir",
        str(output),
    ]
    return argv + (["--no-build-isolation"] if arm == "B" else [])


def backend_epoch(wheel):
    require(digest(wheel) == PDM_HASH, "Publisher backend wheel changed")
    dist = importlib.metadata.distribution("pdm-backend")
    require(dist.version == "2.5.0", "Backend version")
    for item in dist.files:
        if item.hash:
            data = dist.locate_file(item).read_bytes()
            actual = (
                base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                .decode()
                .rstrip("=")
            )
            require(
                item.hash.mode == "sha256"
                and item.hash.value == actual
                and item.size == len(data),
                "Installed backend RECORD integrity",
            )
    with zipfile.ZipFile(wheel) as archive:
        rows = csv.reader(
            io.StringIO(archive.read("pdm_backend-2.5.0.dist-info/RECORD").decode())
        )
        for name, value, size in rows:
            if value:
                data = dist.locate_file(name).read_bytes()
                actual = (
                    base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                    .decode()
                    .rstrip("=")
                )
                require(
                    value == "sha256=" + actual and len(data) == int(size),
                    "Installed publisher RECORD: " + name,
                )
        require(
            archive.read("pdm_backend-2.5.0.dist-info/entry_points.txt")
            .decode()
            .strip()
            == "[console_scripts]\n\n[gui_scripts]",
            "Unexpected backend plugin declaration",
        )
    from pdm import backend

    require(
        backend.get_requires_for_build_sdist()
        == backend.get_requires_for_build_wheel()
        == [],
        "Active dynamic requirements changed",
    )


def payload(context, arm, output):
    rows = []
    if arm == "B":
        started = time.perf_counter()
        backend_epoch(Path(context["pdm"]))
        rows.append(
            {"phase": "candidate-epoch", "seconds": time.perf_counter() - started}
        )
    started = time.perf_counter()
    argv = build_command(context, arm, output)
    completed = subprocess.run(argv, cwd=context["source"], timeout=55)
    rows.append(
        {
            "phase": "complete-sdist-to-wheel",
            "seconds": time.perf_counter() - started,
            "argv": argv,
            "exitcode": completed.returncode,
        }
    )
    save(output.parent / "components.json", rows)
    require(completed.returncode == 0, "Complete build failed")


def caches(source):
    result = {}
    for folder in source.rglob("__pycache__"):
        for path in folder.iterdir():
            if not path.is_file():
                continue
            data = path.read_bytes()
            require(
                path.suffix == ".pyc"
                and len(data) > 16
                and data[:4] == importlib.util.MAGIC_NUMBER,
                "Unknown/PID temporary cache input",
            )
            result[path.relative_to(source).as_posix()] = digest(path)
    return result


def materiality(rows):
    pairs = []
    for offset in (0, 2):
        pair = rows[offset : offset + 2]
        a = next(r["receipt"]["command_wall"] for r in pair if r["arm"] == "A")
        b = next(r["receipt"]["command_wall"] for r in pair if r["arm"] == "B")
        pairs.append(
            {
                "A_seconds": a,
                "B_seconds": b,
                "saving_seconds": a - b,
                "saving_fraction": (a - b) / a,
                "windows_floor": a - b >= 0.5 and (a - b) / a >= 0.1,
            }
        )
    return pairs


def execute(args):
    start = time.monotonic()
    args.output.mkdir()
    result = {
        "status": "STOP",
        "rows": [],
        "scope": "Prepared-project build-only; setup excluded equally, not cold/full-HOBL/parity/adoption",
    }
    helper = archive_helper()
    before = helper.snapshot(args.source)
    initial_caches = caches(args.source)
    context = {
        "source": str(args.source),
        "uv": str(args.uv),
        "cache": str(args.output / "uv-cache"),
        "wheels": str(args.prepared / "wheels"),
        "pdm": str(args.prepared / "wheels" / "pdm_backend-2.5.0-py3-none-any.whl"),
        "constraint": str(args.output / "backend.lock"),
    }
    (args.output / "backend.lock").write_text(
        f"pdm-backend==2.5.0 --hash=sha256:{PDM_HASH}\n"
    )
    require(
        digest(COMMON / "owned_process.py") == GUARD_HASH, "Original guardian identity"
    )
    require(digest(Path(context["pdm"])) == PDM_HASH, "Exact publisher PDM input")
    native = parallel.identity(SimpleNamespace(workers=args.workers))
    require(sys.getswitchinterval() == 0.005, "Expected normal switch interval")
    save(args.output / "native-identity.json", native)
    save(args.output / "source-freeze.json", before)
    save(args.output / "input-plan.json", context)
    save(
        args.output / "freeze.json",
        {
            "schedule": SCHEDULE,
            "script_sha256": digest(Path(__file__)),
            "uv_sha256": digest(args.uv),
            "python_image_sha256": digest(Path(sys.executable)),
            "requirements82_sha256": digest(PARALLEL / "requirements.txt"),
            "installed_hash_lock_sha256": digest(
                args.prepared / "installed-hashes.txt"
            ),
            "guardian_sha256": GUARD_HASH,
            "PDM_sha256": PDM_HASH,
            "source_files": len(before),
            "versions": native["packages"],
            "epoch": 1700000000,
            "native_clock_includes": "fresh helper, B publisher/installed RECORD/dynamic epoch, full sdist then wheel-from-sdist",
            "windows_both_pairs_gate": ">=0.5s and >=10%",
            "mac_value_policy": "report both real treatment pairs; correctness is mandatory, no absolute gain floor",
            "payload_cap_seconds": 60,
            "payload_count": 4,
            "no_warmups_retries": True,
            "setup": "common original82/PDM install and mandatory ujson-last outside BOTH build clocks; never installed FastAPI83",
            "visibility": "explicit trusted shared project environment; not security sandbox/default HOBL",
            "cache_policy": "normal bytecode retained; source-cache additions tracked cohort-wide; backend venv bytecode is normal and unattributed",
        },
    )
    env = os.environ.copy()
    for key in list(env):
        if (
            key.startswith(
                (
                    "UV_",
                    "PYTHON",
                    "PYTEST",
                    "PDM_",
                    "PIP_",
                    "COVERAGE",
                    "COV_CORE",
                    "TIANGOLO_",
                )
            )
            or key == "VIRTUAL_ENV"
        ):
            del env[key]
    env.update(
        SOURCE_DATE_EPOCH="1700000000",
        UV_OFFLINE="1",
        UV_PYTHON_DOWNLOADS="never",
        UV_LINK_MODE="copy",
    )
    result["premeasurement_validation_seconds"] = time.monotonic() - start
    affinity = None
    if sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.GetProcessAffinityMask.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        process = kernel.GetCurrentProcess()
        original, system = ctypes.c_size_t(), ctypes.c_size_t()
        require(
            kernel.GetProcessAffinityMask(
                process, ctypes.byref(original), ctypes.byref(system)
            ),
            "Read owned availability mask",
        )
        available = [1 << n for n in range(64) if original.value & (1 << n)]
        require(len(available) >= 4, "Four owned available Windows LPs")
        mask = sum(available[:4])
        require(kernel.SetProcessAffinityMask(process, mask), "Set owned four-LP mask")
        affinity = (kernel, process, original.value)
        result["owned_affinity"] = {"original": original.value, "used": mask}
    inventory = None
    try:
        for index, arm in enumerate(SCHEDULE, 1):
            folder = args.output / f"payload-{index}"
            folder.mkdir()
            argv = [
                sys.executable,
                str(Path(__file__)),
                "--payload",
                arm,
                "--context",
                str(args.output / "input-plan.json"),
                "--output",
                str(folder / "artifacts"),
            ]
            receipt = run_owned(
                argv,
                cwd=args.source,
                env=env,
                stdout_path=folder / "build.stdout",
                stderr_path=folder / "build.stderr",
                timeout=60,
                native_clock=True,
            )
            row = {
                "index": index,
                "arm": arm,
                "argv": argv,
                "receipt": dataclasses.asdict(receipt),
            }
            result["rows"].append(row)
            save(args.output / "result.json", result)
            require(receipt.succeeded, "First actual build/ownership failure")
            build_log = (folder / "build.stderr").read_text(encoding="utf-8")
            require(
                "Building source distribution" in build_log
                and "Building wheel from source distribution" in build_log,
                "Complete sdist then wheel-from-sdist log stages required",
            )
            audit_start = time.monotonic()
            actual = helper.archives(folder, args.source, before)
            if inventory is None:
                inventory = actual
            require(
                actual == inventory,
                "Complete artifact metadata/payload/RECORD mismatch",
            )
            require(
                helper.snapshot(args.source) == before,
                "Original source identity changed",
            )
            current_caches = caches(args.source)
            require(
                all(current_caches.get(k) == v for k, v in initial_caches.items()),
                "Existing completed caches changed",
            )
            row["new_completed_pycs"] = {
                k: v for k, v in current_caches.items() if k not in initial_caches
            }
            row["audit_seconds_excluded"] = time.monotonic() - audit_start
            row["components"] = json.loads((folder / "components.json").read_text())
            row["audit"] = "PASS"
            save(args.output / "result.json", result)
        result.update(status="COMPLETE", pairs=materiality(result["rows"]))
        result["windows_value_gate"] = all(p["windows_floor"] for p in result["pairs"])
        if sys.platform == "win32":
            require(result["windows_value_gate"], "Windows both-pair materiality floor failed")
    except Exception as error:
        result["reason"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        result["affinity_restored"] = not affinity or bool(
            affinity[0].SetProcessAffinityMask(affinity[1], affinity[2])
        )
        result["source_preserved"] = helper.snapshot(args.source) == before
        result["workflow_component_seconds"] = time.monotonic() - start
        save(args.output / "result.json", result)
        require(result["source_preserved"], "Final source preservation failure")
        require(result["affinity_restored"], "Final owned-affinity restoration failure")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-reviewed", action="store_true")
    parser.add_argument("--payload", choices=("A", "B"))
    parser.add_argument("--context", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int)
    args = parser.parse_args(argv)
    if args.payload:
        payload(json.loads(args.context.read_text()), args.payload, args.output)
    elif args.execute_reviewed:
        require(
            all((args.source, args.prepared, args.uv, args.output, args.workers)),
            "Explicit native inputs required",
        )
        execute(args)
    else:
        parser.exit(
            2,
            "REFUSED: explicit reviewed execution and portable input paths required.\n",
        )


if __name__ == "__main__":
    main()
