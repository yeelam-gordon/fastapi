"""Fail-closed, archive-derived selection for this pinned PDM configuration."""
import contextlib
import fnmatch
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import statistics
import subprocess
import sys
import tarfile
import time
import tomllib

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]


def select(archive, destination):
    entries = archive.getmembers()
    assert all(m.isfile() or m.isdir() for m in entries)
    roots = {PurePosixPath(m.name).parts[0] for m in entries}
    assert len(roots) == 1
    root = roots.pop()
    files = {m.name.removeprefix(root + "/"): m for m in entries if m.isfile()}
    assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts
               for n in files)
    config = tomllib.loads(archive.extractfile(files["pyproject.toml"]).read().decode())
    assert config["build-system"]["build-backend"] == "pdm.backend"
    pdm = config.get("tool", {}).get("pdm", {})
    build = pdm.get("build", {})
    # Other build options can introduce hooks, data inputs or discovery changes.
    assert set(build) <= {"source-includes"}, "Unsupported PDM build configuration"
    assert "pdm_build.py" not in files
    assert not list(importlib.metadata.entry_points(group="pdm.build.hook"))
    assert not any(n.startswith("src/") for n in files), "src discovery unsupported"
    packages = {
        n.split("/")[0] for n in files if len(n.split("/")) == 2
        and (n.endswith("/__init__.py") or
             (n.split("/")[0].endswith("-stubs") and n.endswith("/__init__.pyi")))
    } - {"__pycache__", "__pypackages__"}
    assert packages, "Top-level module fallback unsupported"
    # PDM Builder._get_include_and_exclude excludes declared source-includes
    # from wheels, even if they are otherwise discovered Python packages.
    source_only = [n.rstrip("/") for n in build.get("source-includes", ["tests"])]
    assert all(not any(c in n for c in "*?[") for n in source_only)
    selected = {
        n for n in files if "/" not in n or n.split("/")[0] in packages
    }
    selected = {n for n in selected
                if not any(n == p or n.startswith(p + "/") for p in source_only)}
    project = config["project"]
    assert set(project.get("dynamic", [])) <= {"version"}
    version = pdm.get("version", {})
    assert not version or version.get("source") == "file"
    required = {"pyproject.toml"}
    if version:
        required.add(version["path"])
    readme = project.get("readme")
    if isinstance(readme, str):
        required.add(readme)
    elif isinstance(readme, dict) and "file" in readme:
        required.add(readme["file"])
    license = project.get("license")
    if isinstance(license, dict) and "file" in license:
        required.add(license["file"])
    for pattern in project.get("license-files", ["LICEN[CS]E*", "COPYING*", "NOTICE*"]):
        required.update(n for n in files if fnmatch.fnmatchcase(n, pattern))
    assert required <= selected, f"Metadata input not selected: {required - selected}"
    archive.extractall(destination, members=[files[n] for n in sorted(selected)], filter="data")
    return {"archive_files": len(files), "selected_files": len(selected),
            "packages": sorted(packages), "source_only": source_only,
            "required_metadata_inputs": sorted(required),
            "selected": sorted(selected)}


def child():
    import pdm.backend
    source, output = map(Path, sys.argv[2:])
    artifacts, extracted = output / "artifacts", output / "extracted"
    artifacts.mkdir()
    extracted.mkdir()
    phases = {}

    def phase(name, fn):
        wall, cpu = time.perf_counter(), time.process_time()
        result = fn()
        phases[name] = {"wall": time.perf_counter() - wall,
                        "python_cpu": time.process_time() - cpu}
        return result

    os.chdir(source)
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
        name = phase("sdist", lambda: pdm.backend.build_sdist(str(artifacts)))
        def unpack():
            with tarfile.open(artifacts / name) as archive:
                return select(archive, extracted)
        selection = phase("selection_and_extraction", unpack)
        roots = list(extracted.iterdir())
        assert len(roots) == 1
        os.chdir(roots[0])
        phase("wheel", lambda: pdm.backend.build_wheel(str(artifacts)))
    (output / "phases.json").write_text(json.dumps(phases, indent=2))
    (output / "selection.json").write_text(json.dumps(selection, indent=2))


def main():
    sys.path.insert(0, str(BASE))
    from benchmark import artifact_manifest, compare_manifests
    from experiment import process_cpu
    run = HERE / "selective-refined-run"
    run.mkdir(exist_ok=False)
    source = HERE / "run" / "source"
    python = BASE / "tools" / "official-tool-environment" / "Scripts" / "python.exe"
    reference = artifact_manifest(BASE / "results" / "local-03-canonical" /
                                  "artifacts" / "prepare-baseline")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("UV_", "PIP_")) and k not in ("PYTHONPATH", "PYTHONHOME")}
    temp = run / "temp"
    temp.mkdir()
    env.update(TEMP=str(temp), TMP=str(temp), PYTHONNOUSERSITE="1")
    rows = []
    begin = time.perf_counter()
    for iteration in range(6):
        order = ["full-tar", "selective"] if iteration % 2 == 0 else ["selective", "full-tar"]
        for variant in order:
            trial = run / f"{iteration:02d}-{variant}"
            trial.mkdir()
            if variant == "selective":
                command = [str(python), str(Path(__file__).resolve()), "child",
                           str(source), str(trial)]
            else:
                command = [str(python), str(HERE / "experiment.py"), "child",
                           str(source), str(trial), "tar", "yes"]
            with (trial / "stdout.log").open("wb") as out, (trial / "stderr.log").open("wb") as err:
                start = time.perf_counter()
                process = subprocess.Popen(command, cwd=source, env=env, stdout=out, stderr=err)
                code = process.wait()
                wall = time.perf_counter() - start
                cpu = process_cpu(process._handle)
            row = {"variant": variant, "iteration": iteration, "measured": iteration > 0,
                   "argv": command, "wall_seconds": wall, "returncode": code,
                   "immediate_launcher_cpu_seconds": cpu}
            try:
                assert code == 0, "Build subprocess failed"
                actual = artifact_manifest(trial / "artifacts")
                compare_manifests(reference, actual)
                row["equivalent"] = True
                row["coverage"] = {name: len(members) for name, members in actual.items()}
                (trial / "manifest.json").write_text(json.dumps(actual, indent=2, sort_keys=True))
            except Exception as exc:
                row["equivalent"] = False
                row["failure"] = str(exc)
            for name in ("phases", "selection"):
                p = trial / f"{name}.json"
                if p.exists():
                    row[name] = json.loads(p.read_text())
            rows.append(row)
            (run / "report.json").write_text(json.dumps({"trials": rows}, indent=2))
            print(iteration, variant, round(wall, 4), row.get("failure", "PASS"), flush=True)
    summary = {}
    for variant in ("full-tar", "selective"):
        values = [r["wall_seconds"] for r in rows if r["variant"] == variant
                  and r["measured"] and r["equivalent"]]
        if values:
            summary[variant] = {"median": statistics.median(values), "min": min(values),
                                "max": max(values), "count": len(values)}
    report = {"trials": rows, "summary": summary,
              "experiment_wall_seconds": time.perf_counter() - begin,
              "status": "passed" if all(r["equivalent"] for r in rows) else "failed"}
    (run / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        child()
    else:
        main()
