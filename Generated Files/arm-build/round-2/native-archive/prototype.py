"""Disposable PDM 2.5.0 subclass: native mtree -> sdist -> native extract -> wheel."""
import contextlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
INPUT = LAB / "results" / "local-03-canonical"
MAC = LAB / "results" / "ci-40814588064" / "macos" / "ci" / "artifacts" / "prepare-baseline"
LOCAL = INPUT / "artifacts" / "prepare-baseline"
SOURCE = ROOT / "source"
TAR = Path(os.environ["SystemRoot"]) / "System32" / "tar.exe"
sys.path.insert(0, str(LAB))
import benchmark
from pdm.backend.sdist import SdistBuilder
from pdm.backend.wheel import WheelBuilder
from pdm.backend.utils import safe_version, to_filename
from pdm.backend._vendor.packaging.utils import canonicalize_name


def native(*args):
    result = subprocess.run([str(TAR), *map(str, args)], check=True, capture_output=True, text=True)
    if result.stdout or result.stderr:
        print("NATIVE:", result.stdout, result.stderr)


def escape(value):
    return "".join(f"\\{ord(c):03o}" if c in " \t\r\n\\#=" else c for c in value)


class NativeSdist(SdistBuilder):
    def build_artifact(self, context, files):
        started = time.perf_counter()
        # Parse canonical Git archive-derived permissions anew on every build.
        with tarfile.open(INPUT / "source.tar", "r:") as source_archive:
            modes = {entry.name: entry.mode for entry in source_archive if entry.isfile()}
        name = to_filename(canonicalize_name(context.config.metadata["name"]))
        version = to_filename(safe_version(context.config.metadata["version"]))
        prefix = f"{name}-{version}"
        pkg = context.build_dir / "PKG-INFO"
        pkg.write_bytes(str(self._package_metadata.as_rfc822()).encode("utf-8"))
        rows = ["#mtree", "/set type=file uid=0 gid=0 mode=0644"]
        for inode, (rel, path) in enumerate([*files, ("PKG-INFO", pkg)], 1):
            mode = "0755" if modes.get(rel, 0) & 0o111 else "0644"
            # Logical inode is independent of host filesystem file identifiers.
            rows.append(f"{escape(prefix + '/' + rel)} inode={inode} mode={mode} size={path.stat().st_size} "
                        f"contents={escape(path.resolve().as_posix())}")
        listing = context.build_dir / "archive.mtree"
        listing.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
        target = context.dist_dir / f"{prefix}.tar.gz"
        # A pipe has no archive filesystem identity; avoid bsdtar's false
        # "Can't add archive to itself" exclusion for Windows mtree inputs.
        result = subprocess.run([str(TAR), "-czf", "-", "--format=pax", "@" + str(listing)],
                                check=True, capture_output=True)
        if result.stderr:
            raise RuntimeError(result.stderr.decode(errors="replace"))
        target.write_bytes(result.stdout)
        self.archive_seconds = time.perf_counter() - started
        return target


def build(label):
    output = ROOT / label
    artifacts = output / "artifacts"
    artifacts.mkdir(parents=True)
    extracted = output / "extracted"
    extracted.mkdir()
    start = time.perf_counter()
    with NativeSdist(SOURCE) as builder:
        sdist = builder.build(str(artifacts))
    after_sdist = time.perf_counter()
    native("-xf", sdist, "-C", extracted)
    after_extract = time.perf_counter()
    with WheelBuilder(extracted / sdist.name.removesuffix(".tar.gz")) as builder:
        builder.build(str(artifacts))
    end = time.perf_counter()
    return {"label": label, "seconds": end - start,
            "sdist_seconds": after_sdist - start,
            "extract_seconds": after_extract - after_sdist,
            "wheel_seconds": end - after_extract}


def run_worker(label):
    start = time.perf_counter()
    result = subprocess.run([sys.executable, __file__, "--worker", label],
                            check=True, capture_output=True, text=True)
    elapsed = time.perf_counter() - start
    print(result.stdout, result.stderr)
    row = json.loads((ROOT / label / "timings.json").read_text())
    row["full_process_seconds"] = elapsed
    return row


def main():
    pe = TAR.read_bytes()
    machine = struct.unpack_from("<H", pe, struct.unpack_from("<I", pe, 60)[0] + 4)[0]
    evidence = {"tar": str(TAR), "pe_machine": hex(machine),
                "tar_version": subprocess.check_output([TAR, "--version"], text=True).strip(),
                "pdm_backend": importlib.metadata.version("pdm-backend"),
                "python": sys.version, "git_sha": json.loads((INPUT / "report.json").read_text())["metadata"]["git_sha"]}
    assert machine == 0xAA64
    assert evidence["pdm_backend"] == "2.5.0"
    if not SOURCE.exists():
        shutil.copytree(INPUT / "source", SOURCE, ignore=shutil.ignore_patterns(".pdm-build", "__pycache__"))
    reference = benchmark.artifact_manifest(MAC)
    local = benchmark.artifact_manifest(LOCAL)
    evidence["local_vs_mac"] = [
        {"archive": archive, "member": member, "local": local[archive].get(member), "mac": value}
        for archive, members in reference.items() for member, value in members.items()
        if local[archive].get(member) != value]
    try:
        with (ROOT / "build.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
            evidence["preparation"] = run_worker("prepare")
        actual = benchmark.artifact_manifest(ROOT / "prepare" / "artifacts")
        (ROOT / "prepare-manifest.json").write_text(json.dumps(actual, indent=2))
        differences = [
            {"archive": archive, "member": member, "expected": members.get(member), "actual": actual.get(archive, {}).get(member)}
            for archive, members in reference.items()
            for member in sorted(set(members) | set(actual.get(archive, {})))
            if members.get(member) != actual.get(archive, {}).get(member)]
        evidence["differences"] = differences
        benchmark.compare_manifests(reference, actual)
        evidence["strict_validation"] = "passed: Mac member bytes, sdist execute bits and wheel RECORD"
        trials = evidence["trials"] = []
        with (ROOT / "build.log").open("a", encoding="utf-8") as log, contextlib.redirect_stdout(log):
            for i in range(5):
                trials.append(run_worker(f"trial-{i + 1}"))
                manifest = benchmark.artifact_manifest(ROOT / f"trial-{i + 1}" / "artifacts")
                benchmark.compare_manifests(reference, manifest)
                (ROOT / f"trial-{i + 1}" / "manifest.json").write_text(json.dumps(manifest, indent=2))
        evidence["median_seconds"] = statistics.median(t["seconds"] for t in trials)
        evidence["median_full_process_seconds"] = statistics.median(t["full_process_seconds"] for t in trials)
    except Exception as exc:
        evidence["error"] = repr(exc)
        raise
    finally:
        (ROOT / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        row = build(sys.argv[2])
        (ROOT / sys.argv[2] / "timings.json").write_text(json.dumps(row, indent=2))
    else:
        main()
