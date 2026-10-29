"""Paired ARM protocol v3. Preparation and verification are never build timings."""

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import os
import platform
import shutil
import struct
import subprocess
import sys
import sysconfig
import tarfile
import time
import zipfile
from pathlib import Path, PurePosixPath

SCHEMA = "arm-pairs-v3"
SOURCE = "79cab5bed28b24d92c185d236feb33f5783dfeb3"
ORDERS = (
    ("B", "S1", "S3"),
    ("S3", "S1", "B"),
    ("S1", "B", "S3"),
    ("S3", "B", "S1"),
    ("B", "S3", "S1"),
)
ROOT = Path(__file__).resolve().parents[1]
KNOWN_MODES = {
    f"fastapi-0.162.0/scripts/{name}.sh"
    for name in ("format", "lint", "test", "test-cov", "test-cov-html")
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def native_runtime(system, machine, tag, translated=False):
    arm = machine.lower() in {"arm64", "aarch64"}
    return (
        arm
        and not translated
        and (
            (system == "Windows" and tag.lower().endswith(("arm64", "aarch64")))
            or (system == "Darwin" and ("arm64" in tag or "universal2" in tag))
        )
    )


def binary_receipt(path):
    data = path.read_bytes()
    arm = False
    if data[:2] == b"MZ":
        offset = struct.unpack_from("<I", data, 0x3C)[0]
        arm = (
            data[offset : offset + 4] == b"PE\0\0"
            and struct.unpack_from("<H", data, offset + 4)[0] == 0xAA64
        )
    elif data[:4] == b"\xcf\xfa\xed\xfe":
        arm = struct.unpack_from("<I", data, 4)[0] == 0x100000C
    elif data[:4] in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
        count = struct.unpack_from(">I", data, 4)[0]
        stride = 32 if data[:4] == b"\xca\xfe\xba\xbf" else 20
        arm = any(
            struct.unpack_from(">I", data, 8 + i * stride)[0] == 0x100000C
            for i in range(count)
        )
    if not arm:
        raise ValueError(f"No native ARM64 binary slice: {path}")
    return {"path": str(path.resolve()), "sha256": digest(data), "arm64_slice": True}


def runtime_receipt():
    translated = False
    if sys.platform == "darwin":
        probe = subprocess.run(
            ["sysctl", "-in", "sysctl.proc_translated"], capture_output=True, text=True
        )
        translated = probe.stdout.strip() == "1"
    tag = sysconfig.get_platform()
    native = native_runtime(platform.system(), platform.machine(), tag, translated)
    if not native or sys.version_info[:3] != (3, 13, 15) or struct.calcsize("P") != 8:
        raise ValueError("Requires native ARM64 CPython 3.13.15, not Rosetta")
    library = (
        Path(sys.base_prefix) / "python313.dll"
        if sys.platform == "win32"
        else Path(sysconfig.get_config_var("LIBDIR"))
        / sysconfig.get_config_var("LDLIBRARY")
    )
    executable_receipt = binary_receipt(Path(sys.executable).resolve())
    library_receipt = binary_receipt(library.resolve())
    return {
        "version": platform.python_version(),
        "native_arm64": native,
        "machine": platform.machine(),
        "tag": tag,
        "translated": translated,
        "executable": str(Path(sys.executable).resolve()),
        "executable_sha256": executable_receipt["sha256"],
        "executable_binary": executable_receipt,
        "shared_library": str(library.resolve()),
        "shared_library_sha256": library_receipt["sha256"],
        "shared_library_binary": library_receipt,
        "os": platform.platform(),
        "cores": os.cpu_count(),
        "runner_image": os.environ.get("ImageVersion"),
    }


def volumes(paths):
    import psutil

    partitions = psutil.disk_partitions(all=True)
    result = []
    for path in paths:
        resolved = str(path.resolve())
        matches = [
            p
            for p in partitions
            if resolved.lower().startswith(p.mountpoint.lower().rstrip("\\/") + os.sep)
            or resolved.lower() == p.mountpoint.lower().rstrip("\\/")
        ]
        if not matches:
            raise ValueError(f"No actual volume receipt: {path}")
        part = max(matches, key=lambda p: len(p.mountpoint))
        if sys.platform == "win32" and (
            Path(resolved).drive.lower() != "c:" or part.fstype.lower() != "ntfs"
        ):
            raise ValueError(f"Windows path is not on C: NTFS: {path}: {part}")
        result.append(
            {
                "path": resolved,
                "device": part.device,
                "mountpoint": part.mountpoint,
                "filesystem": part.fstype,
                "trust": "not queried; unchanged",
            }
        )
    return result


def run(argv, log, cwd, env, timeout=120):
    """Track only our process tree; CPU is deliberately unavailable."""
    import psutil

    started = time.perf_counter()
    children = {}
    cleanup_errors = []
    timed_out = False
    with log.open("wb") as stream:
        process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT
        )
        owner = psutil.Process(process.pid)
        while process.poll() is None:
            try:
                children.update({p.pid: p for p in owner.children(recursive=True)})
            except psutil.NoSuchProcess:
                pass
            if time.perf_counter() - started >= timeout:
                timed_out = True
                break
            time.sleep(0.02)
        # Also reject leaked descendants after an otherwise successful wrapper.
        for child in reversed(list(children.values())):
            try:
                if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                    child.kill()
                    child.wait(timeout=5)
                    if not timed_out:
                        cleanup_errors.append(f"Leaked child {child.pid}")
            except psutil.NoSuchProcess:
                pass
            except psutil.Error as exc:
                cleanup_errors.append(str(exc))
        if process.poll() is None:
            process.kill()
        code = process.wait(timeout=10)
    elapsed = time.perf_counter() - started
    return {
        "argv": argv,
        "wall": elapsed,
        "returncode": code,
        "timed_out": timed_out or elapsed > timeout,
        "cleanup_errors": cleanup_errors,
        "cpu_seconds": None,
        "cpu_scope": "unavailable, not launcher CPU",
        "log": str(log),
    }


def succeeded(result):
    return (
        result["returncode"] == 0
        and not result["timed_out"]
        and not result["cleanup_errors"]
        and math.isfinite(result["wall"])
        and result["wall"] > 0
    )


def canonical_source(checkout, output):
    if git(checkout, "rev-parse", "HEAD").decode().strip() != SOURCE:
        raise ValueError("Wrong package source revision")
    archive = output / "canonical-source.tar"
    with archive.open("wb") as stream:
        subprocess.run(
            ["git", "-C", str(checkout), "archive", "--format=tar", SOURCE],
            stdout=stream,
            check=True,
        )
    modes = {}
    for row in git(checkout, "ls-tree", "-rz", SOURCE).split(b"\0"):
        if row:
            header, name = row.split(b"\t", 1)
            mode = int(header.split()[0], 8)
            name = name.decode("utf-8")
            if mode not in (0o100644, 0o100755) or name.startswith("Generated Files/"):
                raise ValueError(f"Noncanonical source input: {name}")
            modes[name] = mode & 0o777
    source = output / "source"
    source.mkdir()
    manifest = {}
    with tarfile.open(archive) as tar:
        for item in tar:
            if item.isdir():
                continue
            name = PurePosixPath(item.name)
            if not item.isfile() or name.is_absolute() or ".." in name.parts:
                raise ValueError(f"Unsafe archive member: {item.name}")
            data = tar.extractfile(item).read()
            mode = modes.pop(item.name)
            target = source.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)
            manifest[item.name] = {
                "mode": mode,
                "sha256": digest(data),
                "size": len(data),
            }
    if modes:
        raise ValueError("Incomplete source archive")
    save(output / "source-manifest.json", manifest)
    return {
        "revision": SOURCE,
        "archive_sha256": digest(archive.read_bytes()),
        "manifest_sha256": digest((output / "source-manifest.json").read_bytes()),
        "files": len(manifest),
    }


def source_matches(source, manifest):
    files = {
        p.relative_to(source).as_posix(): p for p in source.rglob("*") if p.is_file()
    }
    return set(files) == set(manifest) and all(
        digest(files[name].read_bytes()) == info["sha256"]
        and not files[name].is_symlink()
        for name, info in manifest.items()
    )


def inspect_artifacts(directory, oracle):
    """Read archives independently of SDK helpers, never repair their contents."""
    tarballs, wheels = list(directory.rglob("*.tar.gz")), list(directory.rglob("*.whl"))
    if len(tarballs) != 1 or len(wheels) != 1:
        raise ValueError("Expected exactly one complete sdist and wheel")
    actual = {"sdist": {}, "wheel": {}}
    payloads = {}
    with tarfile.open(tarballs[0]) as archive:
        for item in archive:
            if not item.isfile() or item.name in actual["sdist"]:
                raise ValueError(f"Unexpected/duplicate sdist member: {item.name}")
            actual["sdist"][item.name] = {
                "sha256": digest(archive.extractfile(item).read()),
                "mode": item.mode,
                "uid": item.uid,
                "gid": item.gid,
                "uname": item.uname,
                "gname": item.gname,
                "size": item.size,
            }
    with zipfile.ZipFile(wheels[0]) as archive:
        for item in archive.infolist():
            if item.is_dir() or item.filename in payloads:
                raise ValueError(f"Unexpected/duplicate wheel member: {item.filename}")
            data = archive.read(item)
            payloads[item.filename] = data
            actual["wheel"][item.filename] = {
                "sha256": digest(data),
                "full_mode": item.external_attr >> 16,
            }
    record_names = [name for name in payloads if name.endswith(".dist-info/RECORD")]
    if len(record_names) != 1:
        raise ValueError("Expected one RECORD")
    record_name = record_names[0]
    rows = list(csv.reader(io.StringIO(payloads[record_name].decode("utf-8"))))
    record_ok = len(rows) == len(payloads) and all(len(row) == 3 for row in rows)
    record_ok = record_ok and len({row[0] for row in rows}) == len(rows)
    record_ok = record_ok and {row[0] for row in rows} == set(payloads)
    if record_ok:
        for name, checksum, size in rows:
            if name == record_name:
                record_ok &= checksum == size == ""
            else:
                encoded = base64.urlsafe_b64encode(
                    hashlib.sha256(payloads[name]).digest()
                )
                record_ok &= checksum == "sha256=" + encoded.decode().rstrip("=")
                record_ok &= size == str(len(payloads[name]))
    differences = []
    fields = {
        "membership": True,
        "payloads": True,
        "modes": True,
        "ownership": True,
        "metadata": True,
        "record": bool(record_ok),
    }
    for kind in actual:
        if set(actual[kind]) != set(oracle[kind]):
            fields["membership"] = False
            differences.append(
                {
                    "archive": kind,
                    "field": "membership",
                    "missing": sorted(set(oracle[kind]) - set(actual[kind])),
                    "extra": sorted(set(actual[kind]) - set(oracle[kind])),
                }
            )
        for name in actual[kind].keys() & oracle[kind].keys():
            for key, expected in oracle[kind][name].items():
                # RECORD row ordering is harmless only after full self-validation.
                if name == record_name and key == "sha256" and record_ok:
                    continue
                observed = actual[kind][name].get(key)
                if observed != expected:
                    group = (
                        "modes"
                        if key in {"mode", "full_mode"}
                        else "ownership"
                        if key in {"uid", "gid", "uname", "gname"}
                        else "metadata"
                        if name.endswith(("PKG-INFO", "METADATA", "WHEEL"))
                        else "payloads"
                    )
                    fields[group] = False
                    differences.append(
                        {
                            "archive": kind,
                            "name": name,
                            "field": key,
                            "expected": expected,
                            "actual": observed,
                        }
                    )
    fields["metadata"] &= all(
        name in actual["wheel"]
        for name in (
            "fastapi-0.162.0.dist-info/METADATA",
            "fastapi-0.162.0.dist-info/WHEEL",
        )
    )
    return {
        **fields,
        "differences": differences,
        "manifest": actual,
        "counts": {kind: len(items) for kind, items in actual.items()},
        "canonical_record_sha256": digest(json.dumps(sorted(rows)).encode()),
        "record_order_only_policy": "self-validated; all other payloads match oracle",
        "wheel": str(wheels[0]),
    }


def known_baseline_failure(variant, system, check):
    differences = check["differences"]
    return (
        variant == "B"
        and system == "Windows"
        and len(differences) == 5
        and {d.get("name") for d in differences} == KNOWN_MODES
        and all(
            d.get("archive") == "sdist"
            and d.get("field") == "mode"
            and d.get("expected") == 0o755
            and d.get("actual") == 0o644
            for d in differences
        )
        and all(
            check[k]
            for k in (
                "membership",
                "payloads",
                "ownership",
                "metadata",
                "record",
                "source",
                "smoke",
            )
        )
    )


def correct(check):
    return all(
        check.get(key) is True
        for key in (
            "source",
            "membership",
            "payloads",
            "modes",
            "ownership",
            "metadata",
            "record",
            "smoke",
        )
    )


def code_receipts():
    files = [
        *ROOT.joinpath("candidate").glob("*.py"),
        *ROOT.joinpath("protocol").glob("*.py"),
        *ROOT.joinpath("protocol").glob("*.lock"),
        *ROOT.glob("*.lock"),
        ROOT / "setup_python.cjs",
        ROOT / "ci_prepare.py",
        ROOT.parents[1] / ".github" / "workflows" / "arm-build-experiment.yml",
        ROOT / "candidate" / "actual-manifest.json",
    ]
    return {
        p.relative_to(ROOT.parents[1]).as_posix(): digest(p.read_bytes())
        for p in sorted(files)
    }


def smoke(wheel, sample, uv, wheelhouse, env):
    venv = sample / "smoke-env"
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    commands = [
        [uv, "venv", "--no-config", "--python", sys.executable, str(venv)],
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--offline",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "--require-hashes",
            "-r",
            str(ROOT / "smoke.lock"),
        ],
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--offline",
            "--no-deps",
            wheel,
        ],
        [
            str(python),
            "-I",
            "-c",
            "import fastapi; from fastapi import FastAPI; "
            "from fastapi.testclient import TestClient; "
            "app=FastAPI(); app.get('/')(lambda: {'ok': True}); "
            "c=TestClient(app); assert c.get('/').json()=={'ok': True}; "
            "assert c.get('/openapi.json').status_code==200; print(fastapi.__file__)",
        ],
    ]
    records = []
    try:
        for i, command in enumerate(commands):
            result = run(command, sample / f"smoke-{i}.log", sample, env)
            records.append(result)
            if not succeeded(result):
                return False, records
        return True, records
    finally:
        if venv.exists():
            shutil.rmtree(venv)


def prepare(args):
    started = time.perf_counter()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": SCHEMA, "status": "preparing", "commands": []}
    try:
        for required in ("isolated_build.py", "backend.lock"):
            if not (ROOT / "protocol" / required).is_file():
                raise ValueError(f"Integrated caller wrapper required: {required}")
        receipt["runtime"] = runtime_receipt()
        receipt["source"] = canonical_source(args.source_checkout, output)
        wheelhouse = output / "wheelhouse"
        wheelhouse.mkdir()
        commands = [
            [
                args.uv,
                "pip",
                "install",
                "--python",
                sys.executable,
                "--require-hashes",
                "--only-binary",
                ":all:",
                "-r",
                str(ROOT / "tooling.lock"),
            ],
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--require-hashes",
                "-r",
                str(ROOT / "tooling.lock"),
                "-r",
                str(ROOT / "smoke.lock"),
                "-r",
                str(ROOT / "protocol" / "backend.lock"),
                "--dest",
                str(wheelhouse),
            ],
        ]
        # psutil is installed by the first command; preparation is not a sample.
        for i, command in enumerate(commands):
            phase = time.perf_counter()
            with (output / f"prepare-{i}.log").open("wb") as stream:
                result = subprocess.run(
                    command, stdout=stream, stderr=subprocess.STDOUT, timeout=120
                )
            receipt["commands"].append(
                {
                    "argv": command,
                    "returncode": result.returncode,
                    "wall": time.perf_counter() - phase,
                }
            )
            if result.returncode:
                raise ValueError("Dependency preparation failed")
        receipt["wheels"] = {
            p.name: digest(p.read_bytes()) for p in wheelhouse.glob("*.whl")
        }
        receipt["tool_hashes"] = code_receipts()
        receipt["harness_revision"] = git(ROOT, "rev-parse", "HEAD").decode().strip()
        receipt["status"] = "prepared"
    finally:
        receipt["prepare_wall"] = time.perf_counter() - started
        if os.environ.get("PAIR_PROVISION_STARTED"):
            elapsed = time.time() - float(os.environ["PAIR_PROVISION_STARTED"])
            if not math.isfinite(elapsed) or elapsed <= 0:
                raise ValueError("Invalid provisioning wall-clock receipt")
            receipt["runner_provision_wall"] = elapsed
        setup = ROOT / "results" / "bootstrap" / "python-setup.json"
        receipt["python_provision"] = (
            json.loads(setup.read_text()) if setup.exists() else None
        )
        save(output / "prepare.json", receipt)


def measure(args):
    output = args.output.resolve()
    prepared = json.loads((output / "prepare.json").read_text())
    report = {
        "schema": SCHEMA,
        "status": "incomplete",
        "system": platform.system(),
        "source": prepared["source"],
        "harness_revision": prepared["harness_revision"],
        "tool_hashes": code_receipts(),
        "runtime": runtime_receipt(),
        "samples": [],
        "preparation": prepared,
        "schedule": ORDERS,
        "cpu_seconds": None,
        "scopes": {
            "B": "standard_uv_isolated_wall",
            "S1": "sdk_caller_isolated_wall",
            "S3": "sdk_caller_isolated_wall",
        },
        "cache_policy": "warm offline wheels/tools; OS page/security caches uncontrolled",
    }
    env = os.environ.copy()
    env.update(
        UV_OFFLINE="1",
        UV_NO_INDEX="1",
        UV_NO_CONFIG="1",
        UV_PYTHON_DOWNLOADS="never",
        UV_CACHE_DIR=str(output / "uv-cache"),
        UV_FIND_LINKS=str(output / "wheelhouse"),
        TMP=str(output / "temp"),
        TEMP=str(output / "temp"),
        TMPDIR=str(output / "temp"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    for name in ("uv-cache", "temp", "samples"):
        (output / name).mkdir()
    report["environment_changes"] = {
        k: env[k]
        for k in (
            "UV_OFFLINE",
            "UV_NO_INDEX",
            "UV_NO_CONFIG",
            "UV_PYTHON_DOWNLOADS",
            "UV_CACHE_DIR",
            "UV_FIND_LINKS",
            "TMP",
            "TEMP",
            "TMPDIR",
            "PYTHONDONTWRITEBYTECODE",
        )
    }
    try:
        if (
            prepared["status"] != "prepared"
            or report["tool_hashes"] != prepared["tool_hashes"]
        ):
            raise ValueError("Inputs changed after preparation")
        if (
            digest((output / "source-manifest.json").read_bytes())
            != report["source"]["manifest_sha256"]
            or digest((output / "canonical-source.tar").read_bytes())
            != report["source"]["archive_sha256"]
        ):
            raise ValueError("Canonical source receipts changed")
        if {
            p.name: digest(p.read_bytes())
            for p in (output / "wheelhouse").glob("*.whl")
        } != prepared["wheels"]:
            raise ValueError("Offline wheelhouse changed after locked preparation")
        if (
            subprocess.check_output([args.uv, "--version"]).decode().strip()
            != "uv 0.13.6"
        ):
            raise ValueError("Wrong uv version")
        report["uv"] = {"version": "0.13.6", **binary_receipt(Path(args.uv))}
        report["memory_bytes"] = __import__("psutil").virtual_memory().total
        volume_paths = [
            ROOT,
            output,
            Path(sys.executable),
            Path(sys.base_prefix),
            Path(args.uv),
            Path(env["UV_CACHE_DIR"]),
            Path(env["TEMP"]),
        ]
        if env.get("PIP_CACHE_DIR"):
            volume_paths.append(Path(env["PIP_CACHE_DIR"]))
        report["volumes"] = volumes(volume_paths)
        manifest = json.loads((output / "source-manifest.json").read_text())
        oracle = json.loads((ROOT / "candidate" / "actual-manifest.json").read_text())
        if {k: len(v) for k, v in oracle.items()} != {"sdist": 1269, "wheel": 65}:
            raise ValueError("Source-specific oracle requires review")
        for name, info in oracle["sdist"].items():
            relative = name.split("/", 1)[1]
            if relative == "PKG-INFO":
                continue
            canonical = manifest.get(relative)
            if canonical is None or any(
                canonical[key] != info[key] for key in ("sha256", "mode", "size")
            ):
                raise ValueError(f"Oracle disagrees with canonical Git source: {name}")
        for block, order in [(-1, ("B", "S1", "S3")), *enumerate(ORDERS)]:
            for variant in order:
                sample = output / "samples" / f"{block + 1}-{variant}"
                sample.mkdir()
                source = sample / "source"
                shutil.copytree(output / "source", source)
                source_ok = source_matches(source, manifest)
                if not source_ok:
                    raise ValueError("Sample source identity mismatch")
                artifacts = sample / "out"
                if variant == "B":
                    command = [
                        args.uv,
                        "build",
                        str(source),
                        "--sdist",
                        "--wheel",
                        "--out-dir",
                        str(artifacts),
                        "--python",
                        sys.executable,
                        "--offline",
                        "--no-index",
                        "--no-config",
                        "--no-sources",
                        "--find-links",
                        str(output / "wheelhouse"),
                        "--build-constraints",
                        str(ROOT / "protocol" / "backend.lock"),
                        "--require-build-hashes",
                    ]
                else:
                    command = [
                        sys.executable,
                        str(ROOT / "protocol" / "isolated_build.py"),
                        "--uv",
                        args.uv,
                        "--python",
                        sys.executable,
                        "--source",
                        str(source),
                        "--source-manifest",
                        str(output / "source-manifest.json"),
                        "--out-dir",
                        str(artifacts),
                        "--workers",
                        "1" if variant == "S1" else "3",
                        "--cache-dir",
                        env["UV_CACHE_DIR"],
                        "--wheelhouse",
                        str(output / "wheelhouse"),
                        "--report",
                        str(sample / "wrapper.json"),
                    ]
                result = run(command, sample / "build.log", sample, env)
                item = {
                    "block": block,
                    "variant": variant,
                    "timed": block >= 0,
                    "metric": report["scopes"][variant],
                    **result,
                }
                report["samples"].append(item)
                save(output / "report.json", report)
                if not succeeded(result):
                    raise ValueError(f"Sample failed/timeout: {block}/{variant}")
                if variant != "B":
                    item["wrapper_report"] = json.loads(
                        (sample / "wrapper.json").read_text(encoding="utf-8")
                    )
                    if (
                        not isinstance(item["wrapper_report"], dict)
                        or not item["wrapper_report"]
                    ):
                        raise ValueError("Missing caller isolation receipt")
                check = inspect_artifacts(artifacts, oracle)
                check["source"] = source_ok
                check["smoke"], item["smoke_commands"] = smoke(
                    check["wheel"], sample, args.uv, output / "wheelhouse", env
                )
                item["correctness"] = check
                item["known_baseline_mode_failure"] = known_baseline_failure(
                    variant, report["system"], check
                )
                save(sample / "correctness.json", check)
                if not correct(check) and not item["known_baseline_mode_failure"]:
                    raise ValueError(
                        f"Unexpected correctness failure: {block}/{variant}"
                    )
        report["status"] = "complete"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["charged_timed_wall"] = sum(
            s["wall"] for s in report["samples"] if s["timed"]
        )
        report["untimed_smoke_build_wall"] = sum(
            s["wall"] for s in report["samples"] if not s["timed"]
        )
        setup = prepared.get("python_provision") or {}
        provision = prepared.get("runner_provision_wall")
        if provision is None:
            provision = prepared["prepare_wall"] + sum(
                p["seconds"] for p in setup.get("phases", [])
            )
        report["provision_wall"] = provision
        report["provision_plus_all_build_commands"] = provision + sum(
            s["wall"] for s in report["samples"]
        )
        report["total_scope"] = (
            "provision plus 3 smoke builds and up to 15 timed builds; "
            "not cold single-build latency; post-exit verification excluded; "
            "provision runner wall includes tool/source placement, uv setup, "
            "Python acquisition, fixture gate, archive and locked wheel preparation"
        )
        save(output / "report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--source-checkout", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--uv", required=True)
    args = parser.parse_args()
    if args.prepare:
        if args.source_checkout is None:
            parser.error("--prepare needs --source-checkout")
        prepare(args)
    else:
        measure(args)


if __name__ == "__main__":
    main()
