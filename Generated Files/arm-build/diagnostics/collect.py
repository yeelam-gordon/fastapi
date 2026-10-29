"""Analysis only: collect stock uv isolated backend children; never benchmark."""

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import math
import os
import platform
import pstats
import re
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
import zipfile
from pathlib import Path

SOURCE = "79cab5bed28b24d92c185d236feb33f5783dfeb3"
REQUIRED = {
    "get-requires-sdist",
    "build-sdist",
    "get-requires-wheel",
    "build-wheel",
}
PASSES = ("resource", "cprofile", "importtime", "memory")
HERE = Path(__file__).resolve().parent
ENV_KEYS = (
    "CI",
    "RUNNER_OS",
    "RUNNER_ARCH",
    "ImageOS",
    "ImageVersion",
    "PYTHONHASHSEED",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONPYCACHEPREFIX",
    "SOURCE_DATE_EPOCH",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_JOB",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def redact(text, replacements=()):
    for original, replacement in sorted(replacements, key=lambda pair: -len(pair[0])):
        if original:
            text = text.replace(original, replacement)
            text = text.replace(original.replace("\\", "/"), replacement)
    text = re.sub(
        r"(?i)(authorization\s*[:=]\s*)(?:bearer|basic)\s+\S+", r"\1<redacted>", text
    )
    text = re.sub(
        r"(?i)\b(authorization\s*[:=]\s*|(?:token|password|secret|credential|api[_-]?key)\s*[=:]\s*)[^\s,;]+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(r"(?i)(https?://)[^\s/@]+:[^\s/@]+@", r"\1<redacted>@", text)
    text = re.sub(
        r"(?i)([?&](?:access_token|token|key|sig|signature|secret)=)[^&\s]+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)(--(?:token|password|secret|credential|api-key)(?:=|\s+))\S+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(
        r'(?i)("(?:token|password|secret|credential|api_key)"\s*:\s*")[^"]*',
        r"\1<redacted>",
        text,
    )
    text = re.sub(
        r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "<redacted>", text
    )
    return text


def safe_value(value, replacements):
    if isinstance(value, str):
        return redact(value, replacements)
    if isinstance(value, dict):
        return {key: safe_value(item, replacements) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe_value(item, replacements) for item in value]
    return value


def unavailable(reason):
    return {"requested": True, "status": "unavailable", "value": None, "reason": reason}


def cpu_delta(start, end):
    result = {}
    for key in ("user_seconds", "kernel_seconds"):
        first, last = start.get("cpu", {}), end.get("cpu", {})
        if (
            first.get("status") == last.get("status") == "measured"
            and first.get("scope") == last.get("scope") == "self_all_threads"
            and first.get("unit") == last.get("unit") == "seconds"
            and isinstance(first.get(key), (int, float))
            and isinstance(last.get(key), (int, float))
            and math.isfinite(first[key])
            and math.isfinite(last[key])
            and last[key] >= first[key]
        ):
            result[key] = {
                "status": "measured",
                "value": last[key] - first[key],
                "unit": "seconds",
                "scope": "self_all_threads",
                "aggregation": "delta_between_enclosing_snapshot_reads",
            }
        else:
            result[key] = unavailable("Missing/incompatible self CPU counters")
    return result


def counter_status(value):
    """Keep nested platform statuses; truthy unavailable dictionaries are not data."""
    if not isinstance(value, dict):
        return "unavailable"
    if "status" in value:
        return value["status"]
    statuses = [
        counter_status(item) for item in value.values() if isinstance(item, dict)
    ]
    return (
        "measured"
        if statuses and all(item == "measured" for item in statuses)
        else "unavailable"
    )


def profile_export(path, replacements, role=None):
    stats = pstats.Stats(str(path))
    if not stats.stats or not any("pdm" in key[0] for key in stats.stats):
        raise ValueError("Profile lacks actual PDM backend calls")
    symbols = {
        "get-requires-sdist": "get_requires_for_build_sdist",
        "get-requires-wheel": "get_requires_for_build_wheel",
        "build-sdist": "build_sdist",
        "build-wheel": "build_wheel",
    }
    if role in symbols and not any(
        key[2] == symbols[role] and "pdm" in key[0] for key in stats.stats
    ):
        raise ValueError("Profile lacks its identified backend hook")
    rows = []
    for (filename, line, function), (
        primitive,
        calls,
        own,
        cumulative,
        callers,
    ) in stats.stats.items():
        rows.append(
            {
                "file": redact(filename, replacements),
                "line": line,
                "function": function,
                "primitive_calls": primitive,
                "calls": calls,
                "self_seconds": own,
                "cumulative_seconds": cumulative,
                "callers": [
                    {
                        "file": redact(caller[0], replacements),
                        "line": caller[1],
                        "function": caller[2],
                        "stats": list(values) if isinstance(values, tuple) else values,
                    }
                    for caller, values in callers.items()
                ],
            }
        )
    return {
        "status": "measured",
        "timer": "cProfile default elapsed timer",
        "scope": "actual generated backend command after declared bootstrap",
        "performance_eligible": False,
        "full_stats": rows,
        "self_order": sorted(range(len(rows)), key=lambda i: -rows[i]["self_seconds"]),
        "cumulative_order": sorted(
            range(len(rows)), key=lambda i: -rows[i]["cumulative_seconds"]
        ),
        "aggregation": "nested clocks; do not sum cumulative or add to command wall",
    }


def coverage(receipts, identity, mode, upload, replacements=()):
    children, failures = [], []
    starts = list(receipts.glob("*.start.tsv"))
    for path in starts:
        record = {"receipt": path.name, "status": "failed"}
        try:
            fields = path.read_text(encoding="utf-8").strip().split("\t")
            run, actual_mode, role, pid, ppid, start = fields
            if run != identity or actual_mode != mode or path.stem.split(".")[0] != pid:
                raise ValueError("Stale/mismatched start receipt")
            end_path = receipts / f"{pid}.end.json"
            end = json.loads(end_path.read_text(encoding="utf-8"))
            if (
                end.get("identity") != identity
                or end.get("mode") != mode
                or end.get("role") != role
                or end.get("pid") != int(pid)
                or end.get("ppid") != int(ppid)
                or end.get("start_ns") != int(start)
                or end.get("status") != "measured"
                or end.get("end_ns", 0) <= int(start)
                or not isinstance(end.get("wall_seconds"), (int, float))
                or not math.isclose(
                    end["wall_seconds"],
                    (end["end_ns"] - int(start)) / 1e9,
                    rel_tol=1e-9,
                    abs_tol=1e-12,
                )
                or not end.get("scope")
                or end.get("bootstrap_end_ns", int(start) + 1) > int(start)
                or end.get("export_start_ns", 0) < end["end_ns"]
                or end.get("clock") != "monotonic_ns"
                or end.get("performance_eligible") is not False
                or end.get("isolated")
                or end.get("ignore_environment")
                or (
                    role in REQUIRED
                    and end.get("runtime", {}).get("backend_version") != "2.5.0"
                )
            ):
                raise ValueError("Invalid/failed child end receipt")
            snapshots = end.get("snapshots", {})
            end["cpu_delta"] = cpu_delta(
                snapshots.get("start", {}), snapshots.get("end", {})
            )
            end["collector_status"] = {}
            for name in ("cpu", "memory", "io"):
                end["collector_status"][name] = {
                    "requested": True,
                    "status": (
                        "measured"
                        if all(
                            counter_status(snapshots.get(side, {}).get(name))
                            == "measured"
                            for side in ("start", "end")
                        )
                        and not end.get("errors")
                        else "unavailable"
                    ),
                    "reason": "See counter-level statuses and semantics; self only",
                }
            if mode == "cprofile":
                exported = profile_export(
                    receipts / f"{pid}.pstats", replacements, role
                )
                write_json(upload / f"{pid}.profile.json", exported)
                end["profile"] = {"status": "measured", "file": f"{pid}.profile.json"}
            elif mode == "importtime":
                log = (receipts / f"{pid}.imports.raw.log").read_text(
                    encoding="utf-8", errors="replace"
                )
                rows = re.findall(
                    r"^import time:\s+(\d+)\s*\|\s*(\d+)\s*\|\s*(.+)$", log, re.M
                )
                if not rows or not any("pdm" in row[2] for row in rows):
                    raise ValueError("No actual child PDM importtime records")
                (upload / f"{pid}.imports.redacted.log").write_text(
                    redact(log, replacements), encoding="utf-8"
                )
                end["importtime"] = {
                    "status": "measured",
                    "numeric_rows": len(rows),
                    "unit": "microseconds",
                    "early_startup": unavailable(
                        "Before command-entry stderr redirection; frontend log is unassigned"
                    ),
                    "aggregation": "self/cumulative distinct; cumulative clocks overlap",
                }
            elif mode == "memory":
                allocation = end.get("allocation") or {}
                if (
                    allocation.get("status") != "measured"
                    or allocation.get("unit") != "bytes"
                    or not isinstance(allocation.get("peak"), int)
                    or not isinstance(allocation.get("current"), int)
                    or not 0 <= allocation["current"] <= allocation["peak"]
                ):
                    raise ValueError("Invalid Python allocation receipt")
            record = end
        except Exception as error:
            record["reason"] = type(error).__name__ + ": " + str(error)
            failures.append(record["reason"])
        children.append(safe_value(record, replacements))
    orphans = [
        path.name
        for path in receipts.glob("*.end.json")
        if not (receipts / path.name.replace(".end.json", ".start.tsv")).exists()
    ]
    missing = sorted(
        REQUIRED
        - {child.get("role") for child in children if child["status"] == "measured"}
    )
    partial = any(
        counter["status"] != "measured"
        for child in children
        for counter in child.get("collector_status", {}).values()
    )
    return {
        "requested": True,
        "status": "failed"
        if missing or failures or orphans
        else "partial"
        if partial
        else "complete",
        "missing_required_roles": missing,
        "orphan_end_receipts": orphans,
        "children": children,
        "failures": failures,
        "family_cpu": unavailable(
            "Self counters only; no complete frontend/descendant CPU"
        ),
        "frontend_spans": unavailable(
            "Verbose ordering does not measure extraction/installation windows"
        ),
    }


def verify_wheelhouse(directory):
    hashes = json.loads((directory / "sha256.json").read_text(encoding="utf-8"))
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("Empty wheelhouse hash lock")
    actual = {path.name for path in directory.glob("*.whl")}
    if actual != set(hashes):
        raise ValueError("Wheelhouse membership differs from hash lock")
    for name, expected in hashes.items():
        if Path(name).name != name or digest(directory / name) != expected:
            raise ValueError("Wheelhouse hash mismatch")
    backend = directory / "pdm_backend-2.5.0-py3-none-any.whl"
    with zipfile.ZipFile(backend) as archive:
        metadata = archive.read("pdm_backend-2.5.0.dist-info/METADATA").decode()
        if "Version: 2.5.0\n" not in metadata:
            raise ValueError("Unexpected backend version")
    return hashes


def verify_artifact_membership(directory):
    artifacts = list(directory.iterdir())
    marker = directory / ".gitignore"
    if marker in artifacts and marker.is_file() and marker.read_bytes() == b"*":
        artifacts.remove(marker)
    if (
        len(artifacts) != 2
        or sum(path.name.endswith(".whl") for path in artifacts) != 1
        or sum(path.name.endswith(".tar.gz") for path in artifacts) != 1
        or not all(path.is_file() for path in artifacts)
    ):
        raise ValueError("Unexpected build artifact membership")


def canonical_archive(checkout, destination):
    with destination.open("xb") as stream:
        subprocess.run(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "-C",
                str(checkout),
                "archive",
                SOURCE,
            ],
            stdout=stream,
            stderr=subprocess.PIPE,
            check=True,
            timeout=120,
        )
    manifest = {}
    with tarfile.open(destination) as archive:
        for member in archive:
            if member.isdir():
                continue
            if (
                not member.isfile()
                or Path(member.name).is_absolute()
                or ".." in Path(member.name).parts
            ):
                raise ValueError("Unsupported/unsafe canonical source member")
            if member.name in manifest:
                raise ValueError("Duplicate canonical source member")
            manifest[member.name] = {
                "sha256": hashlib.sha256(
                    archive.extractfile(member).read()
                ).hexdigest(),
                "mode": member.mode,
                "size": member.size,
            }
    return manifest


def prepare_source(archive_path, destination, manifest):
    destination.mkdir()
    with tarfile.open(archive_path) as archive:
        archive.extractall(destination, filter="data")
    observed = {}
    for path in destination.rglob("*"):
        if path.is_file():
            observed[path.relative_to(destination).as_posix()] = {
                "sha256": digest(path),
                "mode": path.stat().st_mode & 0o777,
                "size": path.stat().st_size,
            }
    differences = [
        {"path": name, "expected": expected, "actual": observed.get(name)}
        for name, expected in manifest.items()
        if expected != observed.get(name)
    ]
    if observed.keys() != manifest.keys() or any(
        item["actual"] is None
        or item["expected"]["sha256"] != item["actual"]["sha256"]
        or item["expected"]["size"] != item["actual"]["size"]
        for item in differences
    ):
        raise ValueError("Canonical source content/membership mismatch")
    return {"strict_pass": not differences, "differences": differences}


def build_environment(
    base, cache, temporary, hook=None, mode=None, receipts=None, identity=None
):
    env = dict(base)
    for key in list(env):
        if (
            key.startswith(("PYTHON", "UV_", "PDM_", "ARM_DIAG_"))
            or key == "VIRTUAL_ENV"
        ):
            del env[key]
    env.update(
        UV_OFFLINE="1",
        UV_NO_CONFIG="1",
        UV_PYTHON_DOWNLOADS="never",
        UV_CACHE_DIR=str(cache),
        TEMP=str(temporary),
        TMP=str(temporary),
        TMPDIR=str(temporary),
        SOURCE_DATE_EPOCH="1700000000",
    )
    if hook is not None:
        env.update(
            PYTHONPATH=str(hook),
            ARM_DIAG_PASS=mode,
            ARM_DIAG_RECEIPTS=str(receipts),
            ARM_DIAG_ID=identity,
        )
        if mode == "importtime":
            env["PYTHONPROFILEIMPORTTIME"] = "1"
    return env


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context-repeats", type=int, choices=[3], default=3)
    args = parser.parse_args(argv)
    args.uv, args.source_checkout, args.wheelhouse, args.output = (
        path.resolve()
        for path in (args.uv, args.source_checkout, args.wheelhouse, args.output)
    )
    args.output.mkdir(parents=True, exist_ok=False)
    private, upload = args.output / "private_raw", args.output / "upload"
    private.mkdir()
    upload.mkdir()
    identity = uuid.uuid4().hex
    replacements = [
        (str(args.output), "<owned-output>"),
        (str(args.source_checkout), "<checkout>"),
        (str(args.wheelhouse), "<wheelhouse>"),
        (str(Path.home()), "<home>"),
        (sys.base_prefix, "<python-runtime>"),
    ]
    report = {
        "schema": 1,
        "identity": identity,
        "status": "running",
        "performance_eligible": False,
        "analysis_only": True,
        "retention_days": 3,
        "context": [],
        "passes": {},
        "policy": {
            "source": SOURCE,
            "build_timeout_seconds": 120,
            "job_limit_seconds": 1500,
            "retries": 0,
            "context_warmups": 1,
            "context_samples": 3,
            "cache": "owned shared uv cache, initially empty; one context warmup; OS file cache uncontrolled",
            "source_out_temp": "fresh each pass; preparation/verification outside build clock",
            "bytecode": "stock defaults, no injected hook in context; fresh isolated backend environments",
            "isolation": "stock uv default per-stage isolated PDM; wheel from freshly built sdist",
            "network": "offline; only hashed pinned PDM wheel exposed as find-links",
            "native_trace_upload": "never automatic; platform callback receives private_raw only",
        },
        "unavailable": {
            key: unavailable(reason)
            for key, reason in {
                "hook_instrumentation_overhead": "No matched independent overhead estimate",
                "wall_cpu_partition": "Wall and CPU are not disjoint additive intervals",
                "disk_or_scanner_causality": "No inference from elapsed time or process I/O counts",
            }.items()
        },
    }
    started = time.monotonic()

    def persist():
        write_json(upload / "report.json", safe_value(report, replacements))

    try:
        if sys.version_info[:3] != (3, 13, 15):
            raise ValueError("Native CPython 3.13.15 required")
        if platform.machine().lower() not in ("arm64", "aarch64"):
            raise ValueError("Native ARM64 controller required")
        if os.name == "nt" and any(
            path.drive.lower() != "c:"
            for path in (args.uv, args.wheelhouse, args.output, Path(sys.executable))
        ):
            raise ValueError(
                "Windows execution inputs/runtime/output must reside on owned C:"
            )
        version = subprocess.run(
            [str(args.uv), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        if version.split()[:2] != ["uv", "0.13.6"]:
            raise ValueError("Stock uv 0.13.6 required")
        hashes = verify_wheelhouse(args.wheelhouse)
        root = args.source_checkout / "Generated Files" / "arm-build"
        validator = load_module(
            "arm_diag_validator", root / "candidate" / "validate.py"
        )
        expected = json.loads(
            (root / "candidate" / "actual-manifest.json").read_text(encoding="utf-8")
        )
        supervisor = load_module(
            "arm_diag_owned_process", root / "protocol" / "owned_process.py"
        )
        platform_module = load_module(
            "arm_diag_platform", HERE / "arm_diag_platform.py"
        )
        hook = private / "hook"
        shutil.copytree(
            HERE / "hook", hook, ignore=shutil.ignore_patterns("__pycache__")
        )
        shutil.copyfile(HERE / "arm_diag_platform.py", hook / "arm_diag_platform.py")
        inventory = platform_module.inventory(
            [str(args.uv), sys.executable, str(args.output), str(args.wheelhouse)],
            str(private / "inventory"),
        )
        # Inventory adapter owns its schema; publish only its explicitly safe identity map.
        report["platform_inventory"] = inventory
        report["identities"] = {
            "uv": {"version": version, "sha256": digest(args.uv)},
            "python": {
                "version": sys.version,
                "executable_sha256": digest(sys.executable),
                "machine": platform.machine(),
            },
            "environment_whitelist": {key: os.environ.get(key) for key in ENV_KEYS},
            "run": {
                key: os.environ.get(key)
                for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB")
            },
            "code": {
                path.name: digest(path)
                for path in (
                    Path(__file__),
                    HERE / "arm_diag_platform.py",
                    HERE / "hook" / "sitecustomize.py",
                    HERE / "hook" / "arm_diag_hook.py",
                )
            },
            "verification_code_sha256": digest(root / "candidate" / "validate.py"),
            "expected_manifest_sha256": digest(
                root / "candidate" / "actual-manifest.json"
            ),
            "wheelhouse_lock_sha256": digest(args.wheelhouse / "sha256.json"),
            "wheelhouse": hashes,
        }
        archive_path = private / "source.tar"
        manifest = canonical_archive(args.source_checkout, archive_path)
        write_json(upload / "canonical-source-manifest.json", manifest)
        report["identities"]["source_archive_sha256"] = digest(archive_path)
        links, cache = private / "backend-wheels", private / "cache"
        links.mkdir()
        cache.mkdir()
        shutil.copyfile(
            args.wheelhouse / "pdm_backend-2.5.0-py3-none-any.whl",
            links / "pdm_backend-2.5.0-py3-none-any.whl",
        )

        def run_build(label, mode=None):
            if time.monotonic() - started > 1320:
                raise TimeoutError("Job budget exhausted; no additional build")
            workspace, public = private / label, upload / label
            workspace.mkdir()
            public.mkdir()
            source, out, temporary, receipts = (
                workspace / name for name in ("source", "out", "tmp", "receipts")
            )
            source_check = prepare_source(archive_path, source, manifest)
            if time.monotonic() - started > 1320:
                raise TimeoutError("Job budget exhausted during preparation")
            for directory in (out, temporary, receipts):
                directory.mkdir()
            pass_identity = identity + "-" + label
            env = build_environment(
                os.environ,
                cache,
                temporary,
                hook if mode else None,
                mode,
                receipts,
                pass_identity,
            )
            command = [
                str(args.uv),
                "--no-config",
                "build",
                "--python",
                sys.executable,
                "--offline",
                "--no-index",
                "--find-links",
                str(links),
                "--out-dir",
                str(out),
                str(source),
            ]
            if mode == "resource":
                command.append("--verbose")
            began = time.monotonic_ns()
            receipt = supervisor.run_owned(
                command,
                cwd=source,
                env=env,
                stdout_path=workspace / "stdout.raw.log",
                stderr_path=workspace / "stderr.raw.log",
                timeout=120,
            )
            ended = time.monotonic_ns()
            result = {
                "identity": pass_identity,
                "mode": mode or "uninstrumented-context",
                "performance_eligible": False,
                "argv": command,
                "cwd": str(source),
                "start_ns": began,
                "end_ns": ended,
                "clock": "monotonic_ns",
                "scope": "owned supervisor command wall separately from collector wrapper",
                "receipt": dataclasses.asdict(receipt),
                "source_verification": source_check,
                "status": "complete"
                if receipt.succeeded and source_check["strict_pass"]
                else "failed",
                "log_policy": "private original bytes; upload explicitly redacted UTF-8 copies",
            }
            for name in ("stdout", "stderr"):
                raw = workspace / f"{name}.raw.log"
                if raw.exists():
                    (public / f"{name}.redacted.log").write_text(
                        redact(
                            raw.read_text(encoding="utf-8", errors="replace"),
                            replacements,
                        ),
                        encoding="utf-8",
                    )
            if mode:
                result["coverage"] = coverage(
                    receipts, pass_identity, mode, public, replacements
                )
                if result["coverage"]["status"] == "failed":
                    result["status"] = "failed"
                elif (
                    result["coverage"]["status"] == "partial"
                    and result["status"] != "failed"
                ):
                    result["status"] = "partial"
            try:
                verify_artifact_membership(out)
                actual = validator.inventory(out)
                verification = validator.compare(expected, actual)
                write_json(public / "actual-manifest.json", actual)
                result["artifact_verification"] = verification
                if not verification["strict_pass"]:
                    result["status"] = "failed"
            except Exception as error:
                result["artifact_verification"] = {
                    "strict_pass": False,
                    "status": "failed",
                    "reason": str(error),
                }
                result["status"] = "failed"
            write_json(public / "result.json", safe_value(result, replacements))
            return result

        for index in range(4):
            result = run_build("context-warmup" if index == 0 else f"context-{index}")
            report["context"].append(result)
            persist()
        for mode in PASSES:
            report["passes"][mode] = run_build(mode, mode)
            persist()
        native_dir = private / "native"
        native_dir.mkdir()
        report["passes"]["native"] = platform_module.native_capture(
            lambda: run_build("native-build"), str(native_dir)
        )
        if report["passes"]["native"].get("status") != "complete":
            report["status"] = "partial"
        else:
            report["status"] = "complete"
        if any(result["status"] == "failed" for result in report["context"]) or any(
            report["passes"][mode]["status"] == "failed" for mode in PASSES
        ):
            report["status"] = "failed"
        elif any(report["passes"][mode]["status"] == "partial" for mode in PASSES):
            report["status"] = "partial"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "reason": str(error)}
    finally:
        report["collector_wall_seconds"] = time.monotonic() - started
        persist()
    print(
        json.dumps(
            {
                "identity": identity,
                "status": report["status"],
                "report": str(upload / "report.json"),
            }
        )
    )
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
