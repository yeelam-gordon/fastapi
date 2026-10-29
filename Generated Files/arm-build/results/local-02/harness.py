"""Compare isolated and non-isolated PDM builds, without changing production.

Run with the native Python 3.13 interpreter containing pdm-backend (and build
for --importtime). Bootstrap is the caller's responsibility and is NOT timed:

    python benchmark.py --uv <uv executable> --output <NEW results directory>

The source is an immutable git archive of HEAD, not the dirty working tree.
Outputs/cache/logs are retained, including on failure. Two online preparation
builds warm a dedicated shared download cache; measured builds are offline,
alternate order, and build BOTH sdist and wheel-from-sdist. This measures warm
downloads, not cold caches, and not a proposed production configuration.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import sysconfig
import tarfile
import time
import zipfile
from pathlib import Path, PurePosixPath


class VerificationError(ValueError):
    pass


def member_name(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in name.split("/"))
        or ":" in name
    ):
        raise VerificationError(f"Unsafe archive member: {name!r}")
    if "Generated Files" in path.parts:
        raise VerificationError(f"Benchmark artifacts included in package: {name}")
    return str(path)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def wheel_members(path: Path) -> dict[str, str]:
    """Validate every RECORD row before normalizing its generated hash listing."""
    contents: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = member_name(
                info.filename.rstrip("/") if info.is_dir() else info.filename
            )
            if info.is_dir():
                continue
            if name in contents:
                raise VerificationError(f"Duplicate wheel member: {name}")
            contents[name] = archive.read(info)
    records = [name for name in contents if name.endswith(".dist-info/RECORD")]
    if len(records) != 1:
        raise VerificationError("Wheel must contain exactly one RECORD")
    record = records[0]
    signatures = {record + ".jws", record + ".p7s"}
    seen: set[str] = set()
    try:
        rows = csv.reader(io.StringIO(contents[record].decode("utf-8")), strict=True)
        for row in rows:
            if len(row) != 3:
                raise VerificationError(f"Invalid RECORD row: {row!r}")
            name, hashed, size = row
            member_name(name)
            if name in seen or name not in contents:
                raise VerificationError(f"Duplicate or missing RECORD member: {name}")
            seen.add(name)
            if name == record or name in signatures:
                if hashed or size:
                    raise VerificationError(
                        f"RECORD/signature must be unhashed: {name}"
                    )
                continue
            if not hashed or not size:
                raise VerificationError(f"Unhashed RECORD member: {name}")
            algorithm, encoded = hashed.split("=", 1)
            # Wheel hashes must be SHA-256 or stronger; reject weak/unknown hashes.
            if algorithm not in {"sha256", "sha384", "sha512"}:
                raise VerificationError(f"Unsupported RECORD hash: {algorithm}")
            expected = (
                base64.urlsafe_b64encode(
                    hashlib.new(algorithm, contents[name]).digest()
                )
                .rstrip(b"=")
                .decode("ascii")
            )
            if encoded != expected or str(len(contents[name])) != size:
                raise VerificationError(f"RECORD hash/size mismatch: {name}")
    except (UnicodeError, csv.Error, ValueError) as exc:
        raise VerificationError(f"Invalid RECORD in {path.name}: {exc}") from exc
    if set(contents) - signatures != seen - signatures:
        raise VerificationError("RECORD does not cover every wheel member")
    return {
        name: "<verified RECORD>" if name == record else digest(data)
        for name, data in contents.items()
    }


def sdist_members(path: Path) -> dict[str, str]:
    contents: dict[str, str] = {}
    root = path.name.removesuffix(".tar.gz")
    with tarfile.open(path, "r:gz") as archive:
        for info in archive:
            name = member_name(info.name.rstrip("/"))
            parts = PurePosixPath(name).parts
            if parts[0] != root:
                raise VerificationError(f"Unexpected sdist root: {name}")
            if info.isdir():
                continue
            if not info.isfile() or len(parts) < 2:
                raise VerificationError(f"Non-regular sdist member: {name}")
            relative = "/".join(parts[1:])
            if relative in contents:
                raise VerificationError(f"Duplicate sdist member: {relative}")
            stream = archive.extractfile(info)
            assert stream is not None
            contents[relative] = f"{info.mode & 0o111:o}:{digest(stream.read())}"
    if not contents:
        raise VerificationError("Empty sdist")
    return contents


def artifact_manifest(directory: Path) -> dict:
    entries = sorted(directory.iterdir())
    wheels = [p for p in entries if p.name.endswith(".whl")]
    sdists = [p for p in entries if p.name.endswith(".tar.gz")]
    if (
        len(entries) != 2
        or len(wheels) != 1
        or len(sdists) != 1
        or not all(p.is_file() for p in entries)
    ):
        raise VerificationError(
            f"Expected exactly one wheel and one .tar.gz sdist: {entries}"
        )
    return {
        wheels[0].name: wheel_members(wheels[0]),
        sdists[0].name: sdist_members(sdists[0]),
    }


def compare_manifests(expected: dict, actual: dict) -> None:
    if expected.keys() != actual.keys():
        raise VerificationError("Artifact filenames differ")
    for artifact in expected:
        left, right = expected[artifact], actual[artifact]
        if left.keys() != right.keys():
            missing = sorted(left.keys() - right.keys())
            extra = sorted(right.keys() - left.keys())
            raise VerificationError(
                f"{artifact}: member names differ; missing={missing}, extra={extra}"
            )
        changed = [name for name in left if left[name] != right[name]]
        if changed:
            raise VerificationError(f"{artifact}: changed content: {changed}")


class Recorder:
    def __init__(self, output: Path, metadata: dict):
        self.output = output
        self.report = {"status": "running", "metadata": metadata, "commands": []}
        (output / "logs").mkdir()
        self.save()

    def save(self) -> None:
        # Replace just our report, never delete an existing output tree.
        staging = self.output / "report.json.new"
        staging.write_text(json.dumps(self.report, indent=2) + "\n", encoding="utf-8")
        staging.replace(self.output / "report.json")

    def run(self, command: list[str], cwd: Path, phase: str, env: dict) -> str:
        number = len(self.report["commands"])
        prefix = f"{number:03d}-{phase}"
        stdout = self.output / "logs" / f"{prefix}.stdout.log"
        stderr = self.output / "logs" / f"{prefix}.stderr.log"
        record = {
            "argv": [str(arg) for arg in command],
            "cwd": str(cwd),
            "phase": phase,
            "stdout": str(stdout.relative_to(self.output)),
            "stderr": str(stderr.relative_to(self.output)),
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "returncode": None,
        }
        self.report["commands"].append(record)
        self.save()
        started = time.perf_counter()
        try:
            with stdout.open("wb") as out, stderr.open("wb") as err:
                completed = subprocess.run(
                    record["argv"],
                    cwd=cwd,
                    env=env,
                    stdout=out,
                    stderr=err,
                    check=False,
                )
            record["returncode"] = completed.returncode
        except OSError as exc:
            record["launch_error"] = str(exc)
        finally:
            record["wall_seconds"] = time.perf_counter() - started
            self.save()
        if record["returncode"] != 0:
            raise RuntimeError(f"Command failed: {record['argv']}; see {stderr}")
        return stdout.read_text(encoding="utf-8", errors="replace")


def cpu_metadata() -> dict:
    result = {
        "logical_count": os.cpu_count(),
        "processor": platform.processor(),
        "identifier": os.environ.get("PROCESSOR_IDENTIFIER"),
    }
    if sys.platform == "darwin":
        try:
            result["brand"] = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip()
        except (OSError, subprocess.SubprocessError) as exc:
            result["brand_error"] = str(exc)
    return result


def execute(args: argparse.Namespace) -> int:
    interpreter_platform = sysconfig.get_platform().lower()
    if not interpreter_platform.endswith(("arm64", "aarch64")):
        raise ValueError(
            f"Native ARM64 interpreter required, got {interpreter_platform}"
        )
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    generated = source / "Generated Files" / "arm-build" / "results"
    if output == source or (
        source in output.parents and generated not in output.parents
    ):
        raise ValueError(
            "--output must be outside the checkout or under Generated Files/arm-build/results"
        )
    if args.repeats < 5:
        raise ValueError("--repeats must be at least 5")
    # A new directory is required. Never clear or reuse arbitrary caller paths.
    output.mkdir(parents=True, exist_ok=False)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("UV_", "PIP_"))
    }
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    harness = Path(__file__).read_bytes()
    (output / "harness.py").write_bytes(harness)
    recorder = Recorder(
        output,
        {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "interpreter_platform": interpreter_platform,
            "harness_sha256": digest(harness),
            "harness_snapshot": "harness.py",
            "cpu": cpu_metadata(),
            "source_checkout": str(source),
            "source_policy": "git archive HEAD; uncommitted/untracked files excluded",
            "cache_policy": (
                "dedicated shared cache; baseline and candidate online preparation, "
                "then offline measured builds; no cache clearing; NOT cold-cache"
            ),
            "environment_policy": (
                "inherit except UV_*, PIP_*, PYTHONPATH, PYTHONHOME; "
                "PYTHONNOUSERSITE=1; uv --no-config; explicit harness interpreter"
            ),
            "candidate_scope": "diagnostic isolation removal, SAME pdm.backend",
            "repeats": args.repeats,
        },
    )
    try:
        uv = shutil.which(args.uv)
        if uv is None:
            raise ValueError(f"uv executable not found: {args.uv}")
        uv = str(Path(uv).resolve())
        recorder.report["metadata"]["uv"] = recorder.run(
            [uv, "--version"], source, "uv-version", env
        ).strip()
        help_text = recorder.run([uv, "build", "--help"], source, "uv-help", env)
        for flag in (
            "--build-constraints",
            "--no-build-isolation",
            "--python",
            "--no-python-downloads",
            "--no-managed-python",
            "--cache-dir",
            "--no-config",
            "--offline",
            "--no-create-gitignore",
        ):
            if flag not in help_text:
                raise ValueError(f"This uv does not advertise required support: {flag}")
        sha = recorder.run(
            ["git", "rev-parse", "HEAD"], source, "git-head", env
        ).strip()
        recorder.report["metadata"]["git_sha"] = sha
        recorder.report["metadata"]["git_status"] = recorder.run(
            ["git", "status", "--porcelain"], source, "git-status", env
        )
        source_tar = output / "source.tar"
        recorder.run(
            ["git", "archive", "--format=tar", f"--output={source_tar}", sha],
            source,
            "source-snapshot",
            env,
        )
        snapshot = output / "source"
        snapshot.mkdir()
        with tarfile.open(source_tar) as archive:
            archive.extractall(snapshot, filter="data")
        import tomllib

        config = tomllib.loads((snapshot / "pyproject.toml").read_text("utf-8"))
        system = config["build-system"]
        if system.get("build-backend") != "pdm.backend":
            raise ValueError(f"Expected pdm.backend, found {system}")
        packages = {}
        for distribution in importlib.metadata.distributions():
            name = distribution.metadata["Name"]
            if name:
                normalized = name.lower().replace("_", "-").replace(".", "-")
                if normalized in packages:
                    raise ValueError(f"Duplicate installed distribution: {name}")
                packages[normalized] = distribution.version
        if "pdm-backend" not in packages:
            raise ValueError("Preinstall pdm-backend in the harness interpreter")
        if args.importtime and "build" not in packages:
            raise ValueError("Preinstall build for --importtime")
        constraints = output / "build-constraints.txt"
        constraints.write_text(
            "".join(
                f"{name}=={version}\n" for name, version in sorted(packages.items())
            ),
            encoding="utf-8",
        )
        recorder.report["metadata"].update(
            {
                "build_system": system,
                "installed_versions": packages,
                "backend_requirements": importlib.metadata.requires("pdm-backend"),
                "constraints": str(constraints),
                "constraints_sha256": digest(constraints.read_bytes()),
                "constraints_scope": "all installed distributions, including backend/tools",
                "bootstrap_policy": "caller preinstalled dependencies; not included in build timing",
            }
        )
        cache = output / "cache"
        common = [
            uv,
            "build",
            str(snapshot),
            "--python",
            sys.executable,
            "--no-managed-python",
            "--no-python-downloads",
            "--no-config",
            "--build-constraints",
            str(constraints),
            "--cache-dir",
            str(cache),
            "--no-create-gitignore",
        ]
        if getattr(args, "wheelhouse", None):
            wheelhouse = Path(args.wheelhouse).resolve(strict=True)
            common.extend(["--no-index", "--find-links", str(wheelhouse)])
            recorder.report["metadata"]["wheelhouse"] = str(wheelhouse)
            recorder.report["metadata"]["cache_policy"] += (
                "; preparation uses a local wheelhouse, not registry downloads"
            )
        reference = None
        recorder.report["artifacts"] = []

        def build(label: str, phase: str, measured: bool) -> None:
            nonlocal reference
            directory = output / "artifacts" / phase
            directory.mkdir(parents=True)
            command = common + ["--out-dir", str(directory)]
            if label == "candidate":
                command.append("--no-build-isolation")
            if measured:
                command.append("--offline")
            recorder.run(command, snapshot, phase, env)
            manifest = artifact_manifest(directory)
            if reference is None:
                reference = manifest
            else:
                compare_manifests(reference, manifest)
            manifest_path = directory.parent / f"{phase}.manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            recorder.report["artifacts"].append(
                {
                    "phase": phase,
                    "variant": label,
                    "measured": measured,
                    "equivalent": True,
                    "manifest": str(manifest_path.relative_to(output)),
                    "archives": {
                        p.name: {
                            "sha256": digest(p.read_bytes()),
                            "bytes": p.stat().st_size,
                        }
                        for p in directory.iterdir()
                    },
                }
            )
            recorder.save()

        for variant in ("baseline", "candidate"):
            build(variant, f"prepare-{variant}", False)
        for repeat in range(args.repeats):
            order = (
                ("baseline", "candidate")
                if repeat % 2 == 0
                else ("candidate", "baseline")
            )
            for variant in order:
                build(variant, f"repeat-{repeat + 1:02d}-{variant}", True)
        if args.importtime:
            diagnostic = output / "diagnostic"
            diagnostic.mkdir()
            recorder.run(
                [
                    sys.executable,
                    "-X",
                    "importtime",
                    "-m",
                    "build",
                    "--no-isolation",
                    "--outdir",
                    str(diagnostic),
                    str(snapshot),
                ],
                snapshot,
                "diagnostic-importtime-UNMEASURED",
                env,
            )
            compare_manifests(reference, artifact_manifest(diagnostic))
        medians = {}
        ranges = {}
        for variant in ("baseline", "candidate"):
            durations = [
                row["wall_seconds"]
                for row in recorder.report["commands"]
                if row["phase"].startswith("repeat-") and row["phase"].endswith(variant)
            ]
            medians[variant] = statistics.median(durations)
            ranges[variant] = {"min": min(durations), "max": max(durations)}
        recorder.report["summary"] = {
            "median_seconds": medians,
            "range_seconds": ranges,
            "candidate_over_baseline": medians["candidate"] / medians["baseline"],
            "interpretation": "Descriptive warm-download results on this host only",
        }
        recorder.report["status"] = "passed"
        recorder.save()
        return 0
    except Exception as exc:
        recorder.report["status"] = "failed"
        recorder.report["error"] = f"{type(exc).__name__}: {exc}"
        recorder.save()
        print(recorder.report["error"], file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", required=True, help="Path to uv executable")
    parser.add_argument(
        "--output",
        required=True,
        help="NEW output directory; see source/output safety rule",
    )
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument(
        "--importtime", action="store_true", help="Separate untimed build diagnostic"
    )
    parser.add_argument(
        "--wheelhouse",
        help="Use verified local backend wheels instead of registry downloads",
    )
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
