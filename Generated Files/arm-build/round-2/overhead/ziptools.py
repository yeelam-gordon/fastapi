"""Fresh-process PDM tool zipimport; no project metadata or file-list cache."""
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
WHEEL = BASE / "wheelhouse" / "ci-40814042898" / "pdm_backend-2.5.0-py3-none-any.whl"
NATIVE = Path(r"C:\Program Files\Python313-arm64\python.exe")
OFFICIAL = BASE / "tools" / "official-tool-environment" / "Scripts" / "python.exe"


def child():
    tool, source, output = sys.argv[2:]
    start = time.perf_counter()
    if tool != "installed":
        sys.path.insert(0, tool)
    import importlib.metadata
    import pdm.backend
    import pdm.backend.sdist
    import pdm.backend.wheel
    import selective
    evidence = {
        "imports_wall": time.perf_counter() - start,
        "backend_file": pdm.backend.__file__,
        "backend_version": importlib.metadata.version("pdm-backend"),
        "hooks": [str(e) for e in importlib.metadata.entry_points(group="pdm.build.hook")],
        "python": sys.version, "cache_tag": sys.implementation.cache_tag,
        "sys_path": sys.path, "no_site": bool(sys.flags.no_site),
    }
    assert evidence["backend_version"] == "2.5.0" and not evidence["hooks"]
    sys.argv = [__file__, "child", source, output]
    selective.child()
    (Path(output) / "tool.json").write_text(json.dumps(evidence, indent=2))


def provision(run):
    import importlib._bootstrap_external as bytecode
    import importlib.util
    begin = time.perf_counter()
    sources, compiled = run / "tool-source.zip", run / "tool-bytecode.zip"
    with zipfile.ZipFile(WHEEL) as original:
        contents = {i.filename: (i, original.read(i)) for i in original.infolist()}
    directories = {str(parent).replace("\\", "/") + "/"
                   for name in contents for parent in Path(name).parents
                   if str(parent) != "."}
    for path, precompile in [(sources, False), (compiled, True)]:
        start = time.perf_counter()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(directories):
                archive.writestr(name, b"")
            for name, (info, data) in contents.items():
                archive.writestr(info, data)
                if precompile and name.endswith(".py"):
                    code = compile(data, name, "exec", dont_inherit=True, optimize=0)
                    stamp = int(time.mktime(info.date_time + (0, 0, -1)))
                    pyc = bytecode._code_to_timestamp_pyc(code, stamp, len(data))
                    archive.writestr(name + "c", pyc)
        print(path.name, "provision_seconds", time.perf_counter() - start, flush=True)
    return {
        "wall_seconds": time.perf_counter() - begin,
        "source_wheel": str(WHEEL), "source_wheel_sha256": hashlib.sha256(WHEEL.read_bytes()).hexdigest(),
        "python": sys.version, "cache_tag": sys.implementation.cache_tag,
        "magic": importlib.util.MAGIC_NUMBER.hex(),
        "policy": "Unmodified source/metadata preserved; explicit namespace directory entries added. Bytecode ZIP adds timestamp-valid legacy pyc beside each source, optimize=0. No project inputs cached.",
        "files": {p.name: {"bytes": p.stat().st_size,
                            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                  for p in (sources, compiled)},
    }


def main():
    sys.path.insert(0, str(BASE))
    from benchmark import artifact_manifest, compare_manifests
    run = HERE / "ziptools-run"
    run.mkdir(exist_ok=False)
    provisioned = provision(run)
    source = HERE / "run" / "source"
    reference = artifact_manifest(BASE / "results" / "local-03-canonical" /
                                  "artifacts" / "prepare-baseline")
    temp = run / "temp"
    temp.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("UV_", "PIP_")) and k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(TEMP=str(temp), TMP=str(temp), PYTHONNOUSERSITE="1")
    variants = [
        ("installed", [str(OFFICIAL)], "installed"),
        ("sourcezip", [str(NATIVE), "-S"], str(run / "tool-source.zip")),
        ("bytecodezip", [str(NATIVE), "-S"], str(run / "tool-bytecode.zip")),
    ]
    for label, python, tool in variants:
        command = python + ["-X", "importtime", str(Path(__file__).resolve()), "diagnostic", tool]
        with (run / f"{label}-importtime.txt").open("wb") as error:
            result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=error)
        (run / f"{label}-diagnostic.stdout.txt").write_bytes(result.stdout)
        assert result.returncode == 0
    rows = []
    started = time.perf_counter()
    for iteration in range(6):
        order = variants if iteration % 2 == 0 else list(reversed(variants))
        for label, python, tool in order:
            trial = run / f"{iteration:02d}-{label}"
            trial.mkdir()
            command = python + [str(Path(__file__).resolve()), "child", tool,
                                str(source), str(trial)]
            with (trial / "stdout.log").open("wb") as out, (trial / "stderr.log").open("wb") as err:
                start = time.perf_counter()
                result = subprocess.run(command, cwd=source, env=env, stdout=out, stderr=err)
                wall = time.perf_counter() - start
            row = {"variant": label, "iteration": iteration, "measured": iteration > 0,
                   "argv": command, "wall_seconds": wall, "returncode": result.returncode}
            try:
                assert result.returncode == 0, "Build subprocess failed"
                actual = artifact_manifest(trial / "artifacts")
                compare_manifests(reference, actual)
                (trial / "manifest.json").write_text(json.dumps(actual, indent=2, sort_keys=True))
                row["equivalent"] = True
                row["coverage"] = {name: len(members) for name, members in actual.items()}
            except Exception as exc:
                row["equivalent"] = False
                row["failure"] = str(exc)
            for name in ("phases", "selection", "tool"):
                p = trial / f"{name}.json"
                if p.exists():
                    row[name] = json.loads(p.read_text())
            rows.append(row)
            (run / "report.json").write_text(json.dumps({"provision": provisioned, "trials": rows}, indent=2))
            print(iteration, label, round(wall, 4), row.get("failure", "PASS"), flush=True)
    summary = {}
    for label, *_ in variants:
        values = [r["wall_seconds"] for r in rows if r["variant"] == label
                  and r["measured"] and r["equivalent"]]
        if values:
            summary[label] = {"median": statistics.median(values), "min": min(values),
                              "max": max(values), "count": len(values)}
    report = {"provision": provisioned, "trials": rows, "summary": summary,
              "experiment_wall_seconds": time.perf_counter() - started,
              "status": "passed" if all(r["equivalent"] for r in rows) else "failed"}
    (run / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        child()
    elif len(sys.argv) > 1 and sys.argv[1] == "diagnostic":
        tool = sys.argv[2]
        if tool != "installed":
            sys.path.insert(0, tool)
        import importlib.metadata
        import pdm.backend.sdist
        import pdm.backend.wheel
        print(importlib.metadata.version("pdm-backend"))
        print(list(importlib.metadata.entry_points(group="pdm.build.hook")))
    else:
        main()
