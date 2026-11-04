"""Copy versus native-default installer mode; no dispatch/default execution."""

import argparse
import ctypes
import dataclasses
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
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


def native_mode(platform=None):
    platform = sys.platform if platform is None else platform
    require(platform in {"win32", "darwin"}, "Native ARM Windows/macOS only")
    return "hardlink" if platform == "win32" else "clone"


def fallback_evidence(text, mode):
    lines = [
        line
        for line in text.splitlines()
        if "falling back" in line.lower()
        and any(
            word in line.lower()
            for word in ("hardlink", "hard link", "clone", "reflink")
        )
    ]
    return {
        "requested_mode": mode,
        "visible_fallback_lines": lines,
        "implementation": "UNQUALIFIED_FALLBACK_OBSERVED"
        if lines
        else (
            "REQUESTED_COPY"
            if mode == "copy"
            else "REQUESTED_NATIVE_DEFAULT_NO_VISIBLE_FALLBACK"
        ),
        "limit": "Requested mode only; mutable files may copy. No per-file/cache proof. macOS reflink fallback can be debug-only, so absence of normal warnings does not prove cloning.",
    }


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
    mode = "copy" if arm == "A" else native_mode(context["platform"])
    return argv + ["--link-mode", mode]


def payload(context, arm, output):
    rows = []
    started = time.perf_counter()
    argv = build_command(context, arm, output)
    completed = subprocess.run(argv, cwd=context["source"], timeout=55)
    rows.append(
        {
            "phase": "complete-sdist-to-wheel",
            "seconds": time.perf_counter() - started,
            "argv": argv,
            "exitcode": completed.returncode,
            "requested_link_mode": "copy"
            if arm == "A"
            else native_mode(context["platform"]),
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


def require_windows_materiality(rows):
    pairs = materiality(rows)
    require(
        all(pair["windows_floor"] for pair in pairs),
        "Windows both-pair materiality floor failed",
    )
    return pairs


def compare_reports(windows, macos):
    require(
        windows["platform"] == "win32" and macos["platform"] == "darwin",
        "Expected matched ARM platforms",
    )
    require(
        windows["cohort"].get("GITHUB_RUN_ID") and windows["cohort"] == macos["cohort"],
        "One measured cohort required; no mixing runs/orders",
    )
    require(
        windows["protocol"] == macos["protocol"],
        "Matched source/runtime/backend protocol",
    )
    results = []
    for report in (windows, macos):
        require(
            report.get("source_preserved") and report.get("affinity_restored"),
            "Final preservation required",
        )
        require(
            report["status"] == "COMPLETE"
            and report["implementation_no_visible_fallback"],
            "Complete no-visible-fallback correctness required",
        )
        require(
            [r["arm"] for r in report["rows"]] == list(SCHEDULE)
            and all(r.get("audit") == "PASS" for r in report["rows"]),
            "Exactly audited ABBA",
        )
        require(
            all(
                r["receipt"].get("returncode") == 0
                and r["receipt"].get("ownership_established")
                and r["receipt"].get("survivors") is False
                and r["receipt"].get("cleanup_complete")
                and not r["receipt"].get("timed_out")
                and not r["receipt"].get("errors")
                and r["receipt"].get("native_start_ns") is not None
                and r["receipt"].get("native_end_ns") is not None
                for r in report["rows"]
            ),
            "Strict native receipts required",
        )
    require_windows_materiality(windows["rows"])
    for offset in (0, 2):
        win_b = next(
            r["receipt"]["command_wall"]
            for r in windows["rows"][offset : offset + 2]
            if r["arm"] == "B"
        )
        mac_a = next(
            r["receipt"]["command_wall"]
            for r in macos["rows"][offset : offset + 2]
            if r["arm"] == "A"
        )
        mac_b = next(
            r["receipt"]["command_wall"]
            for r in macos["rows"][offset : offset + 2]
            if r["arm"] == "B"
        )
        results.append(
            {
                "order": "AB" if offset == 0 else "BA",
                "Windows_requested_native_B_s": win_b,
                "macOS_copy_A_s": mac_a,
                "macOS_requested_clone_B_s": mac_b,
                "WinB_to_MacA": win_b / mac_a,
                "WinB_to_MacB": win_b / mac_b,
                "observed_no_slower_than_either": win_b <= mac_a and win_b <= mac_b,
            }
        )
    return {
        "orders": results,
        "observed_no_slower_both_orders": all(
            r["observed_no_slower_than_either"] for r in results
        ),
        "limit": "Two-order observed comparison only, not stable/physical parity. Requested native modes, not per-file link proof; macOS silent reflink fallback may be unobservable.",
    }


def execute(args):
    start = time.monotonic()
    args.output.mkdir()
    result = {
        "status": "STOP",
        "rows": [],
        "scope": "Copy versus native-default installer protocol control; not speedup over native-default FastAPI/cold/full-HOBL/stable parity/adoption",
        "platform": sys.platform,
        "cohort": {
            key: os.environ.get(key)
            for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA")
        },
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
        "platform": sys.platform,
    }
    (args.output / "backend.lock").write_text(
        f"pdm-backend==2.5.0 --hash=sha256:{PDM_HASH}\n"
    )
    require(
        digest(COMMON / "owned_process.py") == GUARD_HASH, "Original guardian identity"
    )
    require(digest(Path(context["pdm"])) == PDM_HASH, "Exact publisher PDM input")
    native = parallel.identity(SimpleNamespace(workers=args.workers))
    result["protocol"] = {
        "source_revision": parallel.SOURCE_REVISION,
        "source_manifest_sha256": digest(PARALLEL / "source-manifest.json"),
        "runtime_patch": "3.13.15",
        "uv_version": "0.13.6",
        "PDM_sha256": PDM_HASH,
    }
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
            "native_clock_includes": "fresh helper and complete default-isolated sdist then wheel-from-sdist; no extra B installed-backend epoch",
            "installer_modes": {"A": "copy", "B": native_mode()},
            "windows_both_pairs_gate": ">=0.5s and >=10%",
            "mac_value_policy": "report both real treatment pairs; correctness is mandatory, no absolute gain floor",
            "payload_cap_seconds": 60,
            "payload_count": 4,
            "no_warmups_retries": True,
            "setup": "common original82/PDM install and mandatory ujson-last outside BOTH build clocks; never installed FastAPI83",
            "isolation_logging": "Both default build isolation and normal backend logging; only explicit CLI link-mode differs",
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
    cohort_validated = False
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
            stderr = folder / "build.stderr"
            build_log = stderr.read_text(encoding="utf-8") if stderr.exists() else ""
            row["mode_evidence"] = fallback_evidence(
                build_log, "copy" if arm == "A" else native_mode()
            )
            save(args.output / "result.json", result)
            require(receipt.succeeded, "First actual build/ownership failure")
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
            if arm == "B" and row["mode_evidence"]["visible_fallback_lines"]:
                result["status"] = "IMPLEMENTATION_UNQUALIFIED_FALLBACK"
                result["implementation_no_visible_fallback"] = False
                raise RuntimeError(
                    "Native request visibly fell back; no more payloads or materiality acceptance"
                )
        result["pairs"] = materiality(result["rows"])
        result["windows_value_gate"] = all(p["windows_floor"] for p in result["pairs"])
        result["implementation_no_visible_fallback"] = all(
            not r["mode_evidence"]["visible_fallback_lines"]
            for r in result["rows"]
            if r["arm"] == "B"
        )
        require(
            result["implementation_no_visible_fallback"],
            "Native request fell back: implementation UNQUALIFIED; no materiality acceptance",
        )
        if sys.platform == "win32":
            require_windows_materiality(result["rows"])
        cohort_validated = True
    except Exception as error:
        result["reason"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        result["affinity_restored"] = not affinity or bool(
            affinity[0].SetProcessAffinityMask(affinity[1], affinity[2])
        )
        result["source_preserved"] = helper.snapshot(args.source) == before
        result["workflow_component_seconds"] = time.monotonic() - start
        preserved = result["source_preserved"] and result["affinity_restored"]
        if not preserved:
            result["status"] = "FAILED_FINAL_PRESERVATION"
        elif cohort_validated:
            result["status"] = "COMPLETE"
        save(args.output / "result.json", result)
        require(preserved, "Final source/owned-affinity preservation failure")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-reviewed", action="store_true")
    parser.add_argument(
        "--compare-reports", nargs=2, type=Path, metavar=("WINDOWS", "MACOS")
    )
    parser.add_argument("--payload", choices=("A", "B"))
    parser.add_argument("--context", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int)
    args = parser.parse_args(argv)
    if args.compare_reports:
        require(
            args.output and not args.output.exists(),
            "New explicit comparison output required",
        )
        save(
            args.output,
            compare_reports(*(json.loads(p.read_text()) for p in args.compare_reports)),
        )
    elif args.payload:
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
