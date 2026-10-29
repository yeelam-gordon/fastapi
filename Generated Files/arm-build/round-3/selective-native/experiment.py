"""Screen native selective extraction without weakening archive path filtering."""

import importlib.util
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
spec = importlib.util.spec_from_file_location(
    "integrated_pdm", BASE / "round-2" / "integrated-pdm" / "experiment.py"
)
integrated = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integrated)
native = sys.modules["prototype"]


class NativeExtraction:
    def __init__(self, archive, filename):
        self.archive = archive
        self.filename = filename

    def getmembers(self):
        return self.archive.getmembers()

    def extractfile(self, member):
        return self.archive.extractfile(member)

    def extractall(self, destination, *, members, filter):
        if filter != "data":
            raise ValueError("Only validated data extraction is supported")
        for member in members:
            if tarfile.data_filter(member, str(destination)) is None:
                raise ValueError(f"Unexpected filtered member: {member.name}")
        native.native(
            "-xf", self.filename, "-C", destination, "--", *[m.name for m in members]
        )


def build(source, output, variant):
    if variant == "python":
        return integrated.build(source, output)
    artifacts, extracted = output / "artifacts", output / "extracted"
    artifacts.mkdir()
    extracted.mkdir()
    phases = {}
    started = time.perf_counter()
    with integrated.Candidate(source) as builder:
        sdist = builder.build(str(artifacts))
    phases["sdist"] = time.perf_counter() - started
    started = time.perf_counter()
    with tarfile.open(sdist) as archive:
        selection = integrated.select(NativeExtraction(archive, sdist), extracted)
    phases["selective_extract"] = time.perf_counter() - started
    started = time.perf_counter()
    with integrated.WheelBuilder(
        extracted / sdist.name.removesuffix(".tar.gz")
    ) as builder:
        builder.build(str(artifacts))
    phases["wheel"] = time.perf_counter() - started
    (output / "phases.json").write_text(json.dumps(phases, indent=2))
    (output / "selection.json").write_text(json.dumps(selection, indent=2))


def main():
    source = ROOT / "source"
    if source.exists():
        raise FileExistsError("Prior evidence is retained; choose a fresh experiment")
    shutil.copytree(
        BASE / "results" / "local-03-canonical" / "source",
        source,
        ignore=shutil.ignore_patterns(".pdm-build", "__pycache__"),
    )
    reference = integrated.benchmark.artifact_manifest(native.MAC)
    report = {"status": "running", "trials": []}
    try:
        for iteration in range(6):
            variants = (
                ("python", "native") if iteration % 2 == 0 else ("native", "python")
            )
            for variant in variants:
                output = ROOT / f"trial-{iteration}-{variant}"
                output.mkdir()
                command = [
                    sys.executable,
                    __file__,
                    "--worker",
                    str(source),
                    str(output),
                    variant,
                ]
                with (
                    (output / "stdout.log").open("wb") as out,
                    (output / "stderr.log").open("wb") as err,
                ):
                    started = time.perf_counter()
                    result = subprocess.run(command, cwd=source, stdout=out, stderr=err)
                    seconds = time.perf_counter() - started
                row = {
                    "variant": variant,
                    "seconds": seconds,
                    "measured": iteration > 0,
                    "returncode": result.returncode,
                    "argv": command,
                }
                report["trials"].append(row)
                if result.returncode:
                    raise RuntimeError(f"Build failed: {output}")
                manifest = integrated.benchmark.artifact_manifest(output / "artifacts")
                integrated.benchmark.compare_manifests(reference, manifest)
                row["strict_mac_equivalent"] = True
                row["phases"] = json.loads((output / "phases.json").read_text())
                (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
        report["summary"] = {
            variant: {
                "median": statistics.median(
                    values := [
                        row["seconds"]
                        for row in report["trials"]
                        if row["variant"] == variant and row["measured"]
                    ]
                ),
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }
            for variant in ("python", "native")
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
        build(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    else:
        main()
