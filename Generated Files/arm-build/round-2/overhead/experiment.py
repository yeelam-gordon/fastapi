"""Bounded full-build orchestration comparison; all mutable paths are owned here."""
from __future__ import annotations

import contextlib
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]


def child() -> None:
    # Imports and metadata are deliberately inside the newly started interpreter.
    start = time.perf_counter()
    cpu = time.process_time()
    import tarfile
    import pdm.backend

    source, output, extraction, suppress = sys.argv[2:]
    output = Path(output)
    phases = {}
    phases["startup_imports_wall"] = time.perf_counter() - start
    phases["backend"] = importlib.metadata.version("pdm-backend")

    def phase(name, fn):
        begin, used = time.perf_counter(), time.process_time()
        result = fn()
        phases[name] = {
            "wall": time.perf_counter() - begin,
            "python_cpu": time.process_time() - used,
        }
        return result

    artifacts = output / "artifacts"
    artifacts.mkdir()
    extracted = output / "extracted"
    extracted.mkdir()
    os.chdir(source)
    with contextlib.ExitStack() as stack:
        if suppress == "yes":
            sink = stack.enter_context(open(os.devnull, "w"))
            stack.enter_context(contextlib.redirect_stdout(sink))
            stack.enter_context(contextlib.redirect_stderr(sink))
        sdist = phase("sdist", lambda: pdm.backend.build_sdist(str(artifacts)))

        def unpack():
            if extraction == "tar":
                subprocess.run(
                    [r"C:\Windows\System32\tar.exe", "-xzf", str(artifacts / sdist),
                     "-C", str(extracted)], check=True,
                )
            else:
                with tarfile.open(artifacts / sdist) as archive:
                    archive.extractall(extracted, filter="data")

        phase("extraction", unpack)
        roots = list(extracted.iterdir())
        assert len(roots) == 1 and roots[0].is_dir()
        os.chdir(roots[0])
        # A fresh builder is created by the public hook; no prepared metadata reused.
        phase("wheel", lambda: pdm.backend.build_wheel(str(artifacts)))
    phases["child_wall_after_initial_imports"] = time.perf_counter() - start
    phases["child_python_cpu"] = time.process_time() - cpu
    (output / "phases.json").write_text(json.dumps(phases, indent=2))


def process_cpu(handle):
    values = [ctypes.c_ulonglong() for _ in range(4)]
    ok = ctypes.windll.kernel32.GetProcessTimes(
        ctypes.c_void_p(int(handle)), *(ctypes.byref(v) for v in values)
    )
    return (values[2].value + values[3].value) / 10_000_000 if ok else None


def main() -> None:
    sys.path.insert(0, str(BASE))
    from benchmark import artifact_manifest, compare_manifests

    run = HERE / "run"
    run.mkdir(exist_ok=False)
    source = run / "source"
    shutil.copytree(BASE / "results" / "local-03-canonical" / "source", source)
    reference = artifact_manifest(
        BASE / "results" / "local-03-canonical" / "artifacts" / "prepare-baseline"
    )
    official = BASE / "tools" / "official-tool-environment" / "Scripts" / "python.exe"
    built = BASE / ".venv" / "Scripts" / "python.exe"
    uv = BASE / "tools" / "uv.exe"
    cache, temp = run / "cache", run / "temp"
    cache.mkdir()
    temp.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("UV_", "PIP_")) and k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(TEMP=str(temp), TMP=str(temp), PYTHONNOUSERSITE="1")
    variants = [
        ("uv-official", "uv", official, "python", "no"),
        ("onepy-official-python", "direct", official, "python", "no"),
        ("onepy-official-tar", "direct", official, "tar", "no"),
        ("uv-official-no-logs", "uv", official, "python", "yes"),
        ("onepy-official-tar-no-logs", "direct", official, "tar", "yes"),
        ("onepy-sourcebuilt-tar-no-logs", "direct", built, "tar", "yes"),
    ]
    report = {
        "status": "running", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_commit": "264cbad400c8336057a70b9b6a65bfdb4920321e",
        "host": platform.platform(), "machine": platform.machine(), "cpus": os.cpu_count(),
        "reference": str(BASE / "results" / "local-03-canonical" / "artifacts" / "prepare-baseline"),
        "policy": "Full fresh subprocess wall includes interpreter/import/metadata/sdist/extraction/wheel/logs. Source snapshot copy, validation and provisioning excluded. Warm local filesystem; offline; owned same-Q cache/temp; no global changes.",
        "concurrency_limit": "Only this worker serial; other workers may run independent experiments on the same host.",
        "cpu_scope": "GetProcessTimes of immediate child only: uv excludes backend descendants; direct excludes tar child. Not total process-tree CPU.",
        "trials": [], "failures": [],
    }

    def save():
        (run / "report.json").write_text(json.dumps(report, indent=2))

    overall = time.perf_counter()
    save()
    for iteration in range(6):
        order = variants if iteration % 2 == 0 else list(reversed(variants))
        for label, kind, python, extraction, suppress in order:
            trial = run / f"{iteration:02d}-{label}"
            trial.mkdir()
            if kind == "uv":
                artifacts = trial / "artifacts"
                command = [
                    str(uv), "build", str(source), "--python", str(python),
                    "--no-build-isolation", "--no-managed-python",
                    "--no-python-downloads", "--no-config", "--offline",
                    "--no-create-gitignore", "--cache-dir", str(cache),
                    "--out-dir", str(artifacts),
                ]
                if suppress == "yes":
                    command.append("--no-build-logs")
            else:
                command = [str(python), str(Path(__file__).resolve()), "child",
                           str(source), str(trial), extraction, suppress]
                artifacts = trial / "artifacts"
            row = {"variant": label, "iteration": iteration,
                   "measured": iteration > 0, "argv": command, "cwd": str(source)}
            with (trial / "stdout.log").open("wb") as out, (trial / "stderr.log").open("wb") as err:
                begin = time.perf_counter()
                process = subprocess.Popen(command, cwd=source, env=env, stdout=out, stderr=err)
                row["returncode"] = process.wait()
                row["wall_seconds"] = time.perf_counter() - begin
                row["immediate_child_cpu_seconds"] = process_cpu(process._handle)
            try:
                assert row["returncode"] == 0, "Build subprocess failed"
                actual = artifact_manifest(artifacts)
                compare_manifests(reference, actual)
                (trial / "manifest.json").write_text(json.dumps(actual, indent=2, sort_keys=True))
                row["equivalent"] = True
                row["coverage"] = {name: len(members) for name, members in actual.items()}
                row["archive_bytes"] = {p.name: p.stat().st_size for p in artifacts.iterdir()}
            except Exception as exc:
                row["equivalent"] = False
                row["failure"] = str(exc)
                report["failures"].append(row)
            phases = trial / "phases.json"
            if phases.exists():
                row["phases"] = json.loads(phases.read_text())
            report["trials"].append(row)
            save()
            print(iteration, label, round(row["wall_seconds"], 4),
                  "PASS" if row["equivalent"] else row.get("failure"), flush=True)
    report["summary"] = {}
    for label, *_ in variants:
        values = [r["wall_seconds"] for r in report["trials"]
                  if r["variant"] == label and r["measured"] and r["equivalent"]]
        if values:
            report["summary"][label] = {
                "count": len(values), "median": statistics.median(values),
                "min": min(values), "max": max(values), "all": values,
            }
    report["experiment_wall_seconds"] = time.perf_counter() - overall
    report["status"] = "passed" if not report["failures"] else "failed"
    save()
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        child()
    else:
        main()
