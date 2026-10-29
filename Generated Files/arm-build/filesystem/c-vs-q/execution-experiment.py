"""Disposable pinned-PDM override; every measured child builds from fresh inputs."""
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
INPUT = Path(os.environ["LAB_INPUT"])
WORK = Path(os.environ["LAB_WORK"])
SOURCE = Path(os.environ["LAB_SOURCE"])


def backend(node):
    import subprocess
    from pdm.backend.sdist import SdistBuilder
    from pdm.backend.utils import safe_version, to_filename
    from pdm.backend._vendor.packaging.utils import canonicalize_name

    class NodeSdist(SdistBuilder):
        def clock(self):
            return time.perf_counter() if self.diagnostic else 0

        def mark(self, name, start):
            if self.diagnostic:
                self.stages[name] = time.perf_counter() - start

        def initialize(self, context):
            start = self.clock()
            super().initialize(context)
            self.mark("pdm_initialize", start)

        def get_files(self, context):
            start = self.clock()
            result = super().get_files(context)
            self.mark("fresh_pdm_selection", start)
            return result

        def build_artifact(self, context, files):
            start = self.clock()
            data = json.loads((INPUT / "source-manifest.json").read_text())
            modes = {name: value["mode"] for name, value in data.items()}
            self.mark("permission_manifest_read", start)
            start = self.clock()
            prefix = (to_filename(canonicalize_name(context.config.metadata["name"])) + "-" +
                      to_filename(safe_version(context.config.metadata["version"])))
            pkg = context.build_dir / "PKG-INFO"
            pkg.write_bytes(str(self._package_metadata.as_rfc822()).encode("utf-8"))
            self.mark("fresh_pkg_info", start)
            start = self.clock()
            rows = []
            for rel, source in files:
                if rel not in modes:
                    raise ValueError(f"Unmanifested source member: {rel}")
                rows.append({"name": prefix + "/" + rel, "source": str(source.absolute()),
                             "mode": 0o755 if modes[rel] & 0o111 else 0o644})
            rows.append({"name": prefix + "/PKG-INFO", "source": str(pkg.absolute()), "mode": 0o644})
            request = json.dumps({"root": str(SOURCE), "workers": self.workers,
                                  "diagnostic": self.diagnostic,
                                  "files": rows}).encode("utf-8")
            self.mark("fresh_ipc_manifest", start)
            start = self.clock()
            result = subprocess.run([node, str(HERE / "writer.cjs")], input=request,
                                    capture_output=True, check=True)
            if result.stderr:
                if not self.diagnostic:
                    raise RuntimeError(result.stderr.decode())
                self.stages["node_internal"] = json.loads(result.stderr)
            target = context.dist_dir / f"{prefix}.tar.gz"
            target.write_bytes(result.stdout)
            self.mark("node_start_io_tar_gzip_and_output", start)
            return target
    return NodeSdist


def child(label, workers, diagnostic, node):
    start = time.perf_counter()
    cpu = time.process_time()
    import tarfile
    NodeSdist = backend(node)
    from pdm.backend.wheel import WheelBuilder
    from selective_inputs import select
    imported = time.perf_counter()
    output = WORK / label
    artifacts, extracted = output / "artifacts", output / "extracted"
    artifacts.mkdir(parents=True)
    extracted.mkdir()
    with NodeSdist(SOURCE) as builder:
        builder.workers = workers
        builder.diagnostic = diagnostic
        builder.stages = {}
        sdist = builder.build(str(artifacts))
    after_sdist = time.perf_counter()
    with tarfile.open(sdist) as archive:
        selection = select(archive, extracted)
    after_extract = time.perf_counter()
    roots = list(extracted.iterdir())
    assert len(roots) == 1
    with WheelBuilder(roots[0]) as wheel:
        wheel.build(str(artifacts))
    end = time.perf_counter()
    row = {"python_cpu_seconds": time.process_time() - cpu, "label": label, "workers": workers, "child_seconds": end - start,
           "imports_seconds": imported - start, "sdist_seconds": after_sdist - imported,
           "select_extract_seconds": after_extract - after_sdist,
           "wheel_seconds": end - after_extract}
    if diagnostic:
        row["stages"] = builder.stages
        row["coordinator_modules_loaded"] = {
            name: name in sys.modules for name in ("benchmark", "statistics")}
    (HERE / f"{label}-timings.json").write_text(json.dumps(row, indent=2))
    (HERE / f"{label}-selection.json").write_text(json.dumps(selection, indent=2))


def main():
    import hashlib
    import importlib.metadata
    import os
    import shutil
    import statistics
    import subprocess
    sys.path.insert(0, str(LAB))
    import benchmark
    node = shutil.which("node")
    mac = LAB / "results" / "ci-40814588064" / "macos" / "ci" / "artifacts" / "prepare-baseline"
    assert importlib.metadata.version("pdm-backend") == "2.5.0"
    WORK.mkdir(exist_ok=True)
    (WORK / "runtime").mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("UV_", "PIP_")) and k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(TEMP=str(WORK / "runtime"), TMP=str(WORK / "runtime"),
               PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PDM_BUILD_NO_CLEAN", None)
    runtime = json.loads(subprocess.check_output(
        [node, "-p", "JSON.stringify({version:process.version,arch:process.arch})"], text=True))
    assert runtime == {"version": "v24.21.0", "arch": "arm64"}, runtime
    reference = benchmark.artifact_manifest(mac)
    evidence = {"node": node, "runtime": runtime, "python": sys.executable,
                "pdm_backend": importlib.metadata.version("pdm-backend"),
                "source_manifest_sha256": hashlib.sha256(
                    (INPUT / "source-manifest.json").read_bytes()).hexdigest(),
                "reference": str(mac), "target_seconds": 0.730,
                "timing_boundary": "parent spawn through child exit; imports, fresh PDM selection/"
                "metadata, Node IPC/startup/IO/gzip9, completed-sdist selection/extraction, fresh wheel",
                "excluded": ["source checkout copy", "installed tool bootstrap", "post-build validation"],
                "trials": []}
    if not SOURCE.exists():
        shutil.copytree(INPUT / "source", SOURCE,
                        ignore=shutil.ignore_patterns(".pdm-build", "__pycache__"))

    def run(label, workers=4, diagnostic=False):
        command = [sys.executable, str(HERE / "experiment.py"), "--child", label,
                   str(workers), str(int(diagnostic)), node]
        with (HERE / f"{label}.stdout.log").open("wb") as out, (
                HERE / f"{label}.stderr.log").open("wb") as err:
            begin = time.perf_counter()
            result = subprocess.run(command, env=env, stdout=out, stderr=err)
            elapsed = time.perf_counter() - begin
        if result.returncode:
            raise RuntimeError(f"{label} exited {result.returncode}; see stderr log")
        row = json.loads((HERE / f"{label}-timings.json").read_text())
        row.update(full_process_seconds=elapsed, command=command)
        actual = benchmark.artifact_manifest(WORK / label / "artifacts")
        benchmark.compare_manifests(reference, actual)
        row["strict_mac_validation"] = "passed"
        row["members"] = {name: len(members) for name, members in actual.items()}
        (HERE / f"{label}-manifest.json").write_text(json.dumps(actual, indent=2))
        return row

    try:
        evidence["preparation"] = run("prepare")
        for i in range(5):
            evidence["trials"].append(run(f"trial-{i + 1}"))
        evidence["diagnostics"] = [run("diagnostic-4", 4, True),
                                   run("diagnostic-8", 8, True)]
        evidence["medians"] = {key: statistics.median(row[key] for row in evidence["trials"])
                               for key in ("full_process_seconds", "child_seconds", "imports_seconds",
                                           "sdist_seconds", "select_extract_seconds", "wheel_seconds")}
        evidence["strict_validation"] = "passed: preparation, five trials, both diagnostics"
        evidence["parity_target_met"] = evidence["medians"]["full_process_seconds"] <= 0.730
    except Exception as exc:
        evidence["error"] = repr(exc)
        raise
    finally:
        (HERE / "evidence.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence["medians"], indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(sys.argv[2], int(sys.argv[3]), bool(int(sys.argv[4])), sys.argv[5])
    else:
        main()
