"""Bounded follow-up: source-checkout permission manifest, not cached build output."""
import contextlib
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tarfile
import time

import prototype as original
from pdm.backend.sdist import SdistBuilder

ROOT = original.ROOT / "manifest-candidate"
SOURCE = original.SOURCE


class Candidate(SdistBuilder):
    diagnostic = False
    mode_source = "json"

    def mark(self, name, started):
        if self.diagnostic:
            self.stages[name] = time.perf_counter() - started

    def initialize(self, context):
        start = time.perf_counter() if self.diagnostic else 0
        super().initialize(context)
        self.mark("pdm_initialize", start)

    def get_files(self, context):
        start = time.perf_counter() if self.diagnostic else 0
        files = super().get_files(context)
        self.mark("fresh_pdm_collect_and_validate", start)
        return files

    def build_artifact(self, context, files):
        start = time.perf_counter() if self.diagnostic else 0
        if self.mode_source == "archive":
            with tarfile.open(original.INPUT / "source.tar", "r:") as archive:
                modes = {entry.name: entry.mode for entry in archive if entry.isfile()}
        else:
            data = json.loads((original.INPUT / "source-manifest.json").read_text())
            modes = {name: value["mode"] for name, value in data.items()}
        self.mark("permission_input_parse", start)
        start = time.perf_counter() if self.diagnostic else 0
        name = original.to_filename(original.canonicalize_name(context.config.metadata["name"]))
        version = original.to_filename(original.safe_version(context.config.metadata["version"]))
        prefix = f"{name}-{version}"
        pkg = context.build_dir / "PKG-INFO"
        pkg.write_bytes(str(self._package_metadata.as_rfc822()).encode("utf-8"))
        self.mark("fresh_pkg_info_generation", start)
        start = time.perf_counter() if self.diagnostic else 0
        rows = ["#mtree", "/set type=file uid=0 gid=0 mode=0644"]
        for inode, (rel, path) in enumerate([*files, ("PKG-INFO", pkg)], 1):
            mode = "0755" if modes.get(rel, 0) & 0o111 else "0644"
            rows.append(f"{original.escape(prefix + '/' + rel)} inode={inode} mode={mode} "
                        f"size={path.stat().st_size} contents={original.escape(path.resolve().as_posix())}")
        listing = context.build_dir / "archive.mtree"
        listing.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
        self.mark("stat_path_and_mtree_generation", start)
        start = time.perf_counter() if self.diagnostic else 0
        result = subprocess.run([str(original.TAR), "-czf", "-", "--format=pax", "@" + str(listing)],
                                check=True, capture_output=True)
        if result.stderr:
            raise RuntimeError(result.stderr.decode(errors="replace"))
        self.mark("native_gzip_writer_pipe", start)
        start = time.perf_counter() if self.diagnostic else 0
        target = context.dist_dir / f"{prefix}.tar.gz"
        target.write_bytes(result.stdout)
        self.mark("compressed_output_write", start)
        return target


def build(label, diagnostic=False, mode_source="json"):
    output = ROOT / label
    artifacts = output / "artifacts"
    artifacts.mkdir(parents=True)
    extracted = output / "extracted"
    extracted.mkdir()
    start = time.perf_counter()
    with Candidate(SOURCE) as builder:
        builder.stages = {}
        builder.diagnostic = diagnostic
        builder.mode_source = mode_source
        sdist = builder.build(str(artifacts))
    after_sdist = time.perf_counter()
    original.native("-xf", sdist, "-C", extracted)
    after_extract = time.perf_counter()
    with original.WheelBuilder(extracted / sdist.name.removesuffix(".tar.gz")) as wheel:
        wheel.build(str(artifacts))
    end = time.perf_counter()
    return {"label": label, "seconds": end - start,
            "sdist_seconds": after_sdist - start,
            "extract_seconds": after_extract - after_sdist,
            "wheel_seconds": end - after_extract, "diagnostic_stages": builder.stages}


def validate(label, reference):
    manifest = original.benchmark.artifact_manifest(ROOT / label / "artifacts")
    original.benchmark.compare_manifests(reference, manifest)
    (ROOT / label / "manifest.json").write_text(json.dumps(manifest, indent=2))


def main():
    ROOT.mkdir()
    reference = original.benchmark.artifact_manifest(original.MAC)
    evidence = {"diagnostics_are_untimed": True, "diagnostics": [], "trials": []}
    try:
        with tarfile.open(original.INPUT / "source.tar", "r:") as archive:
            archived = {entry.name: entry.mode for entry in archive if entry.isfile()}
        supplied = json.loads((original.INPUT / "source-manifest.json").read_text())
        assert archived == {name: value["mode"] for name, value in supplied.items()}
        evidence["permission_proof"] = {"all_git_modes_equal": True, "files": len(archived),
            "source_manifest_sha256": hashlib.sha256((original.INPUT / "source-manifest.json").read_bytes()).hexdigest()}
        with (ROOT / "build.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
            for mode in ("archive", "json"):
                label = "diagnostic-" + mode
                evidence["diagnostics"].append(build(label, True, mode))
                validate(label, reference)
            listing = SOURCE / ".pdm-build" / "archive.mtree"
            controls = []
            for flags in (["--version"], ["-cf", "-", "--format=pax", "@" + str(listing)],
                          ["-czf", "-", "--format=pax", "--options=gzip:compression-level=1", "@" + str(listing)]):
                start = time.perf_counter()
                result = subprocess.run([str(original.TAR), *flags], check=True, capture_output=True)
                assert not result.stderr, result.stderr
                controls.append({"args": flags, "seconds": time.perf_counter() - start,
                                 "output_bytes": len(result.stdout)})
            evidence["untimed_writer_controls"] = controls
            for i in range(5):
                label = f"trial-{i + 1}"
                start = time.perf_counter()
                result = subprocess.run([sys.executable, __file__, "--worker", label],
                                        check=True, capture_output=True, text=True)
                elapsed = time.perf_counter() - start
                print(result.stdout, result.stderr)
                row = json.loads((ROOT / label / "timings.json").read_text())
                row["full_process_seconds"] = elapsed
                evidence["trials"].append(row)
                validate(label, reference)
        evidence["medians"] = {key: statistics.median(row[key] for row in evidence["trials"])
                               for key in ("full_process_seconds", "seconds", "sdist_seconds", "extract_seconds", "wheel_seconds")}
        evidence["strict_validation"] = "passed: both diagnostic builds and five full-process candidate builds"
    finally:
        (ROOT / "evidence.json").write_text(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        row = build(sys.argv[2])
        (ROOT / sys.argv[2] / "timings.json").write_text(json.dumps(row, indent=2))
    else:
        main()
