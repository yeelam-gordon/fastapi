"""Combine the two verified PDM optimizations without changing project sources."""

import hashlib
import json
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]
sys.path[:0] = [
    str(BASE / "round-2" / "native-archive"),
    str(BASE / "round-2" / "overhead"),
    str(BASE),
]
import benchmark
from manifest_candidate import Candidate
from pdm.backend.wheel import WheelBuilder
from selective import select


def build(source, output):
    artifacts, extracted = output / "artifacts", output / "extracted"
    artifacts.mkdir()
    extracted.mkdir()
    phases = {}
    started = time.perf_counter()
    with Candidate(source) as builder:
        sdist = builder.build(str(artifacts))
    phases["sdist"] = time.perf_counter() - started
    started = time.perf_counter()
    with tarfile.open(sdist) as archive:
        selection = select(archive, extracted)
    phases["selective_extract"] = time.perf_counter() - started
    started = time.perf_counter()
    with WheelBuilder(extracted / sdist.name.removesuffix(".tar.gz")) as builder:
        builder.build(str(artifacts))
    phases["wheel"] = time.perf_counter() - started
    (output / "phases.json").write_text(json.dumps(phases, indent=2))
    (output / "selection.json").write_text(json.dumps(selection, indent=2))


def main():
    source = ROOT / "source"
    if source.exists():
        raise FileExistsError(
            "Use a new experiment directory; prior evidence is retained"
        )
    shutil.copytree(
        BASE / "results" / "local-03-canonical" / "source",
        source,
        ignore=shutil.ignore_patterns(".pdm-build", "__pycache__"),
    )
    reference = benchmark.artifact_manifest(
        BASE
        / "results"
        / "ci-40814588064"
        / "macos"
        / "ci"
        / "artifacts"
        / "prepare-baseline"
    )
    report = {
        "status": "running",
        "scope": "Full fresh process; complete native sdist, selective archive inputs, fresh PDM wheel",
        "source_sha": "264cbad400c8336057a70b9b6a65bfdb4920321e",
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "trials": [],
    }
    try:
        for index in range(6):
            output = ROOT / f"trial-{index}"
            output.mkdir()
            command = [sys.executable, __file__, "--worker", str(source), str(output)]
            with (
                (output / "stdout.log").open("wb") as out,
                (output / "stderr.log").open("wb") as err,
            ):
                started = time.perf_counter()
                result = subprocess.run(command, cwd=source, stdout=out, stderr=err)
                seconds = time.perf_counter() - started
            row = {
                "argv": command,
                "returncode": result.returncode,
                "seconds": seconds,
                "measured": index > 0,
            }
            report["trials"].append(row)
            if result.returncode:
                raise RuntimeError(f"Trial {index} failed; see retained stderr")
            actual = benchmark.artifact_manifest(output / "artifacts")
            benchmark.compare_manifests(reference, actual)
            row["strict_mac_equivalent"] = True
            row["phases"] = json.loads((output / "phases.json").read_text())
            (output / "manifest.json").write_text(json.dumps(actual, indent=2))
        samples = [row["seconds"] for row in report["trials"] if row["measured"]]
        report["summary"] = {
            "median_seconds": statistics.median(samples),
            "min_seconds": min(samples),
            "max_seconds": max(samples),
            "count": len(samples),
        }
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        raise
    finally:
        (ROOT / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        build(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        main()
