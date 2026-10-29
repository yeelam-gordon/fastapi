"""Compare downloaded native ARM CI artifacts; never run or download builds.

Usage: python compare_ci.py --windows WINDOWS_DIR --macos MACOS_DIR --output NEW.json

Each root must contain exactly one report.json. Recorded paths are resolved
relative to that report, independent of the original runner's absolute paths.
Archives may be omitted in synthetic fixtures or reduced downloads: manifests
are still checked, but raw archive verification is explicitly unknown and the
overall result cannot pass. Bootstrap reports are optional and never counted as
zero seconds. Output is created exclusively, including on comparison failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

import benchmark


class ComparisonError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ComparisonError(message)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: expected JSON object")
    return value


def identity(path: Path) -> dict:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def relative_file(directory: Path, name: str) -> Path:
    # JSON paths were written by Windows or POSIX Python.
    parts = PurePosixPath(name.replace("\\", "/"))
    require(
        not parts.is_absolute()
        and bool(parts.parts)
        and all(part not in (".", "..") and ":" not in part for part in parts.parts),
        f"Unsafe recorded path: {name}",
    )
    path = directory.joinpath(*parts.parts)
    require(
        path.resolve().is_relative_to(directory.resolve()), f"Escaping path: {name}"
    )
    return path


def seconds(value: object, context: str) -> float:
    require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0,
        f"{context}: expected finite positive duration",
    )
    return float(value)


def version(value: str, kind: str) -> str:
    pattern = (
        r"uv (\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)(?:\s.*)?"
        if kind == "uv"
        else r"(\d+\.\d+\.\d+)(?:\s.*)?"
    )
    match = re.fullmatch(pattern, value)
    require(match is not None, f"Invalid {kind} version: {value!r}")
    assert match is not None
    return match[1]


def optional_report(root: Path, name: str) -> dict:
    paths = sorted(root.rglob(name))
    require(len(paths) <= 1, f"Ambiguous {name} under {root}")
    if not paths:
        return {"status": "unknown", "reason": f"{name} not supplied"}
    report = read_json(paths[0])
    require(report.get("status") == "passed", f"{name}: status is not passed")
    commands = report.get("commands", [])
    require(bool(commands), f"{name}: no completed commands")
    for row in commands:
        require(row.get("returncode") == 0, f"{name}: failed/incomplete command")
    result = {
        "status": "passed",
        "input": identity(paths[0]),
        "phases_seconds": {
            row["phase"]: seconds(row.get("seconds"), name) for row in commands
        },
    }
    if name == "smoke.json":
        require(
            {"smoke-dependencies", "install-artifact", "artifact-smoke"}
            <= {row["phase"] for row in commands},
            "smoke.json: missing runtime smoke phases",
        )
    return result


def manifest_shape(manifest: dict) -> None:
    require(
        len(manifest) == 2
        and sum(name.endswith(".whl") for name in manifest) == 1
        and sum(name.endswith(".tar.gz") for name in manifest) == 1,
        "Manifest must contain one wheel and one sdist",
    )
    for archive, members in manifest.items():
        require(isinstance(members, dict) and bool(members), "Empty artifact manifest")
        for name, value in members.items():
            benchmark.member_name(name)
            pattern = (
                r"(?:[01]{1,3}):[a-f0-9]{64}"
                if archive.endswith(".tar.gz")
                else r"[a-f0-9]{64}|<verified RECORD>"
            )
            require(
                isinstance(value, str) and re.fullmatch(pattern, value) is not None,
                f"Invalid manifest entry: {archive}: {name}",
            )


def load_run(root: Path, label: str) -> tuple[dict, dict, dict]:
    reports = sorted(root.rglob("report.json"))
    require(len(reports) == 1, f"{label}: expected exactly one report.json")
    path = reports[0]
    report = read_json(path)
    require(report.get("status") == "passed", f"{label}: build status is not passed")
    metadata = report["metadata"]
    platform_tag = metadata["interpreter_platform"].lower()
    native = (
        platform_tag == "win-arm64"
        if label == "windows"
        else metadata["machine"].lower() in {"arm64", "aarch64"}
        and platform_tag.endswith(("arm64", "aarch64", "universal2"))
    )
    require(native, f"{label}: interpreter is not native ARM64")
    require(
        (label == "windows" and platform_tag.startswith("win"))
        or (label == "macos" and platform_tag.startswith("macosx")),
        f"{label}: unexpected interpreter platform {platform_tag}",
    )
    require(
        metadata["build_system"]["build-backend"] == "pdm.backend",
        f"{label}: expected pdm.backend",
    )
    backend = metadata["installed_versions"]["pdm-backend"]
    require(
        isinstance(backend, str) and bool(backend), f"{label}: missing backend version"
    )
    versions = {
        "source_sha": metadata["git_sha"],
        "python_patch": version(metadata["python"], "Python"),
        "uv_semver": version(metadata["uv"], "uv"),
        "pdm_backend": backend,
        "build_system": metadata["build_system"],
    }
    require(
        re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", versions["source_sha"])
        is not None,
        f"{label}: invalid source SHA",
    )
    for key, filename in (
        ("harness_sha256", "harness.py"),
        ("constraints_sha256", "build-constraints.txt"),
    ):
        if key in metadata:
            local = path.parent / filename
            require(local.is_file(), f"{label}: missing {filename}")
            require(
                identity(local)["sha256"] == metadata[key],
                f"{label}: {filename} digest mismatch",
            )

    commands = report["commands"]
    require(bool(commands), f"{label}: no commands")
    indexed = {}
    for row in commands:
        require(row.get("returncode") == 0, f"{label}: failed/incomplete command")
        require(row["phase"] not in indexed, f"{label}: duplicate command phase")
        indexed[row["phase"]] = row
    samples = {"baseline": [], "candidate": []}
    measured = set()
    workload = None
    repeat_ids = {"baseline": set(), "candidate": set()}
    for phase, row in indexed.items():
        if not phase.startswith("repeat-"):
            continue
        match = re.fullmatch(r"repeat-(\d+)-(baseline|candidate)", phase)
        require(match is not None, f"{label}: malformed measured phase {phase}")
        assert match is not None
        variant = match[2]
        argv = row["argv"]
        require(
            "--offline" in argv and "build" in argv,
            f"{label}: timed build is not offline",
        )
        require(
            ("--no-build-isolation" in argv) == (variant == "candidate"),
            f"{label}: incorrect isolation flags",
        )
        require("--out-dir" in argv, f"{label}: missing build output argument")
        normalized = list(argv)
        output_index = normalized.index("--out-dir") + 1
        require(output_index < len(normalized), f"{label}: missing output directory")
        normalized[output_index] = "<output>"
        normalized = [arg for arg in normalized if arg != "--no-build-isolation"]
        if workload is None:
            workload = normalized
        require(normalized == workload, f"{label}: measured build workloads differ")
        samples[variant].append(seconds(row.get("wall_seconds"), phase))
        repeat_ids[variant].add(int(match[1]))
        measured.add(phase)
    require(
        repeat_ids["baseline"] == repeat_ids["candidate"]
        and len(repeat_ids["baseline"]) >= 5,
        f"{label}: need at least five paired baseline/candidate samples",
    )
    require(
        repeat_ids["baseline"] == set(range(1, len(samples["baseline"]) + 1)),
        f"{label}: incomplete repeat sequence",
    )
    if "repeats" in metadata:
        require(
            metadata["repeats"] == len(samples["baseline"]),
            f"{label}: declared repeats mismatch",
        )

    reference = None
    seen = set()
    archive_status = "unknown"
    archive_checks = []
    for row in report["artifacts"]:
        phase = row["phase"]
        require(phase not in seen, f"{label}: duplicate artifact phase")
        seen.add(phase)
        require(phase in indexed, f"{label}: artifact lacks build command")
        require(row.get("equivalent") is True, f"{label}: unequal artifact")
        require(
            row.get("variant") in samples
            and phase.endswith("-" + row["variant"])
            and row.get("measured") is (phase in measured),
            f"{label}: artifact sample metadata mismatch",
        )
        manifest_path = relative_file(path.parent, row["manifest"])
        manifest = read_json(manifest_path)
        manifest_shape(manifest)
        if reference is None:
            reference = manifest
        else:
            benchmark.compare_manifests(reference, manifest)
        require(
            row["archives"].keys() == manifest.keys(),
            f"{label}: declared archives differ from manifest",
        )
        archive_directory = manifest_path.parent / phase
        if archive_directory.exists():
            actual = benchmark.artifact_manifest(archive_directory)
            benchmark.compare_manifests(manifest, actual)
            for name, recorded in row["archives"].items():
                archive = archive_directory / name
                require(
                    identity(archive)["sha256"] == recorded["sha256"]
                    and archive.stat().st_size == recorded["bytes"],
                    f"{label}: raw archive digest/size mismatch: {name}",
                )
            archive_checks.append({"phase": phase, "status": "passed"})
            if phase == "prepare-baseline":
                archive_status = "passed"
    require(
        measured <= seen and {"prepare-baseline", "prepare-candidate"} <= seen,
        f"{label}: missing preparation or timed manifests",
    )
    assert reference is not None
    timings = {
        variant: {
            "count": len(values),
            "median_seconds": statistics.median(values),
            "range_seconds": {"min": min(values), "max": max(values)},
            "samples_seconds": values,
        }
        for variant, values in samples.items()
    }
    baseline = timings["baseline"]["median_seconds"]
    candidate = timings["candidate"]["median_seconds"]
    summary = report.get("summary", {})
    if summary:
        for variant in samples:
            require(
                summary["median_seconds"][variant] == timings[variant]["median_seconds"]
                and summary["range_seconds"][variant]
                == timings[variant]["range_seconds"],
                f"{label}: reported summary disagrees with samples",
            )
        require(
            math.isclose(summary["candidate_over_baseline"], candidate / baseline),
            f"{label}: reported isolation ratio disagrees with samples",
        )
    result = {
        "input_report": identity(path),
        "native_platform": {
            key: metadata.get(key)
            for key in ("platform", "machine", "interpreter_platform", "cpu")
        },
        "versions": versions,
        "build_only": timings,
        "local_isolation": {
            "candidate_over_baseline": candidate / baseline,
            "baseline_over_candidate_speedup": baseline / candidate,
            "median_seconds_saved": baseline - candidate,
            "fraction_saved": 1 - candidate / baseline,
        },
        "normalized_artifacts": "passed",
        "raw_reference_archives": {
            "status": archive_status,
            "checked": archive_checks,
            "reason": (
                "Reference wheel/sdist verified against manifest and archive hashes"
                if archive_status == "passed"
                else "prepare-baseline archives absent; not verified"
            ),
        },
        "bootstrap": optional_report(root, "provision.json"),
        "runtime_smoke": optional_report(root, "smoke.json"),
    }
    return result, reference, metadata


def cross_manifests(left: dict, right: dict) -> dict:
    try:
        benchmark.compare_manifests(left, right)
        return {"status": "passed", "exact_normalized_equality": True}
    except benchmark.VerificationError as exc:
        diagnostic = str(exc)
    # Windows sdists may lack executable bits retained by macOS. Do not mask
    # them: compare hashes, retain every changed mode, and report non-equality.
    require(left.keys() == right.keys(), diagnostic)
    differences = []
    for archive in left:
        require(left[archive].keys() == right[archive].keys(), diagnostic)
        for name, expected in left[archive].items():
            actual = right[archive][name]
            if expected == actual:
                continue
            require(archive.endswith(".tar.gz"), diagnostic)
            left_mode, left_hash = expected.split(":", 1)
            right_mode, right_hash = actual.split(":", 1)
            require(left_hash == right_hash, diagnostic)
            differences.append(
                {
                    "archive": archive,
                    "member": name,
                    "windows_executable_bits": left_mode,
                    "macos_executable_bits": right_mode,
                }
            )
    require(bool(differences), diagnostic)
    return {
        "status": "equivalent-build-content-with-mode-differences",
        "exact_normalized_equality": False,
        "diagnostic": diagnostic,
        "executable_mode_differences": differences,
        "interpretation": (
            "Same source SHA, sdist member contents, and verified wheel contents; "
            "build workload remains equivalent. Sdist executable semantics differ "
            "and are not claimed equal; runtime smoke tests only the wheel."
        ),
    }


def compare(windows: Path, macos: Path) -> dict:
    result = {
        "status": "failed",
        "inputs": {},
        "limits": (
            "Descriptive warm-download offline build-only timings, not statistical "
            "durability. Bootstrap install/download phases are separate; CI queue "
            "and total job times are unknown. Logical CPU counts do not establish "
            "physical 20-vs-16-core performance."
        ),
    }
    try:
        # Capture input identities even if validation subsequently fails.
        for label, root in (("windows", windows), ("macos", macos)):
            paths = sorted(root.rglob("report.json"))
            result["inputs"][label] = [identity(path) for path in paths]
        win, left, win_metadata = load_run(windows, "windows")
        result["windows"] = win
        mac, right, mac_metadata = load_run(macos, "macos")
        result["macos"] = mac
        require(
            win["versions"] == mac["versions"], "Source/toolchain versions mismatch"
        )
        if "harness_sha256" in win_metadata or "harness_sha256" in mac_metadata:
            require(
                win_metadata.get("harness_sha256")
                == mac_metadata.get("harness_sha256"),
                "Benchmark harness mismatch",
            )
        result["normalized_artifact_check"] = cross_manifests(left, right)
        ratios = {
            variant: (
                win["build_only"][variant]["median_seconds"]
                / mac["build_only"][variant]["median_seconds"]
            )
            for variant in ("baseline", "candidate")
        }
        result["windows_over_macos_build_only_medians"] = ratios
        verified = all(
            run["runtime_smoke"]["status"] == "passed"
            and run["raw_reference_archives"]["status"] == "passed"
            for run in (win, mac)
        )
        result["status"] = "passed" if verified else "unknown"
        result["windows_le_macos_goal"] = {
            variant: "met"
            if verified and ratio <= 1
            else "not-met"
            if verified
            else "unknown"
            for variant, ratio in ratios.items()
        }
        result["conclusion"] = (
            "Validated equivalent build-content workloads; see per-variant median goals."
            if verified
            else "Comparison incomplete: raw reference archives or runtime smoke unknown."
        )
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        IndexError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["conclusion"] = "Comparison rejected; no performance goal established."
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--macos", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        with args.output.open("x", encoding="utf-8") as stream:
            result = compare(args.windows, args.macos)
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{result['status']}: {result['conclusion']}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
