"""Profile actual PDM backend phases separately from uv benchmark samples."""

import argparse
import cProfile
import importlib.metadata
import io
import json
import os
import pstats
import tarfile
import time
from pathlib import Path

import pdm.backend
from benchmark import artifact_manifest, compare_manifests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, help="Immutable benchmark source snapshot"
    )
    parser.add_argument(
        "--reference", required=True, help="Verified baseline artifact directory"
    )
    parser.add_argument(
        "--output", required=True, help="New diagnostic output directory"
    )
    args = parser.parse_args()
    source = Path(args.source).resolve(strict=True)
    reference = Path(args.reference).resolve(strict=True)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifacts = output / "artifacts"
    artifacts.mkdir()
    report = {
        "backend": importlib.metadata.version("pdm-backend"),
        "source": str(source),
        "interpretation": "Untimed diagnostic relative to benchmark; profiler adds overhead",
        "phases": {},
        "status": "running",
    }

    def profile(phase, function):
        profiler = cProfile.Profile()
        started = time.perf_counter()
        result = profiler.runcall(function, str(artifacts))
        seconds = time.perf_counter() - started
        profiler.dump_stats(str(output / f"{phase}.pstats"))
        text = io.StringIO()
        stats = pstats.Stats(profiler, stream=text)
        stats.strip_dirs().sort_stats("cumulative").print_stats(40)
        (output / f"{phase}.txt").write_text(
            text.getvalue().rstrip() + "\n", encoding="utf-8"
        )
        report["phases"][phase] = {"profiled_seconds": seconds, "artifact": result}
        return result

    original_directory = Path.cwd()
    try:
        os.chdir(source)
        sdist = profile("sdist", pdm.backend.build_sdist)
        unpacked = output / "source"
        unpacked.mkdir()
        with tarfile.open(artifacts / sdist) as archive:
            archive.extractall(unpacked, filter="data")
        roots = list(unpacked.iterdir())
        if len(roots) != 1 or not roots[0].is_dir():
            raise RuntimeError("Expected one sdist source root")
        os.chdir(roots[0])
        profile("wheel", pdm.backend.build_wheel)
        compare_manifests(artifact_manifest(reference), artifact_manifest(artifacts))
        report["status"] = "passed"
        report["artifacts_equivalent"] = True
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        os.chdir(original_directory)
        (output / "profile.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
