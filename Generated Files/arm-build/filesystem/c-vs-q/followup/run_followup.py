"""One fresh C checkout, shared unchanged tools/environment, fresh per-build outputs."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
import zipfile

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
import run

ROOT = Path(r"C:\fastapi-arm-build-lab\copilot-2a73e36a")
WORK = ROOT / "followup-shared-checkout"
PYTHON = ROOT / "env" / "Scripts" / "python.exe"
receipt = {"status": "preparing", "trials": [], "commands": [],
           "boundary": "spawn through child exit; stdout/stderr captured in memory and published after timer",
           "source_policy": "ONE new canonical checkout reused for all builds; PDM cleans and regenerates metadata each build",
           "profile_policy": "one separately profiled sdist-only build; not a clean timing sample",
           "protection_policy": "no ETW, exclusions, protection/global changes or CI"}


def save():
    (HERE / "evidence.json").write_text(json.dumps(receipt, indent=2))


def execute(command, env, cwd, label):
    begin = time.perf_counter()
    process = subprocess.Popen([str(x) for x in command], env=env, cwd=cwd,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    elapsed = time.perf_counter() - begin
    creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
    api = ctypes.WinDLL("kernel32", use_last_error=True).GetProcessTimes
    api.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    success = api(wintypes.HANDLE(int(process._handle)), ctypes.byref(creation),
                  ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user))
    ticks = lambda value: (value.dwHighDateTime << 32) + value.dwLowDateTime
    row = {"label": label, "argv": [str(x) for x in command], "cwd": str(cwd),
           "full_process_seconds": elapsed, "returncode": process.returncode,
           "launcher_cpu_seconds": (ticks(kernel) + ticks(user)) / 1e7 if success else None,
           "cpu_scope": "immediate launched process only; uv backend descendants excluded",
           "stdout": f"{label}.stdout.log", "stderr": f"{label}.stderr.log"}
    (HERE / row["stdout"]).write_bytes(stdout)
    (HERE / row["stderr"]).write_bytes(stderr)
    receipt["commands"].append(row)
    save()
    if process.returncode:
        raise RuntimeError(f"{label} exited {process.returncode}: {stderr.decode(errors='replace')}")
    return row, stdout.decode(errors="replace"), stderr.decode(errors="replace")


def wheel_exec(directory):
    with zipfile.ZipFile(next(directory.glob("*.whl"))) as archive:
        return {member.filename: bool((member.external_attr >> 16) & 0o111)
                for member in archive.infolist() if not member.is_dir()}


def main():
    assert not WORK.exists(), "Never overwrite an existing follow-up workspace"
    begin = time.perf_counter()
    WORK.mkdir()
    source, code = WORK / "source", WORK / "code"
    source.mkdir()
    code.mkdir()
    for name in ("temp", "cache", "outputs"):
        (WORK / name).mkdir()
    shutil.copyfile(HERE / "worker.py", code / "worker.py")
    shutil.copyfile(PARENT / "execution-selective_inputs.py", code / "selective_inputs.py")
    shutil.copyfile(run.UV, code / "uv.exe")
    manifest_path = ROOT / "inputs" / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    with tarfile.open(ROOT / "inputs" / "source.tar") as archive:
        archive.extractall(source, filter="data")
    for name, info in manifest.items():
        assert run.sha(source / name) == info["sha256"]
    receipt.update(source=str(source), python=str(PYTHON),
        canonical_commit="264cbad400c8336057a70b9b6a65bfdb4920321e",
        source_inventory_files=len(manifest), source_preparation_seconds=time.perf_counter() - begin,
        mode_manifest_sha256=run.sha(manifest_path),
        worker_sha256=run.sha(code / "worker.py"), selector_sha256=run.sha(code / "selective_inputs.py"))
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("UV_", "PIP_")) and k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(TEMP=str(WORK / "temp"), TMP=str(WORK / "temp"),
               LOCALAPPDATA=str(WORK / "cache"), XDG_CACHE_HOME=str(WORK / "cache"),
               PDM_CACHE_DIR=str(WORK / "cache"), UV_CACHE_DIR=str(WORK / "cache"),
               PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PDM_BUILD_NO_CLEAN", None)
    receipt["controlled_environment"] = {key: env[key] for key in
        ("TEMP", "TMP", "LOCALAPPDATA", "XDG_CACHE_HOME", "PDM_CACHE_DIR", "UV_CACHE_DIR",
         "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE")}
    expected = run.members(run.MAC)
    expected_exec = wheel_exec(run.MAC)
    execute([code / "uv.exe", "--version"], env, source, "uv-version")
    receipt["status"] = "running"
    save()
    for iteration in range(1, 4):
        order = ["uv", "full", "selective"] if iteration % 2 else ["uv", "selective", "full"]
        for variant in order:
            label = f"{iteration}-{variant}"
            output = WORK / "outputs" / label
            output.mkdir()
            if variant == "uv":
                artifacts = output / "artifacts"
                artifacts.mkdir()
                command = [code / "uv.exe", "build", "--no-build-isolation", "--python", PYTHON,
                           "--offline", "--no-config", "--out-dir", artifacts]
            else:
                artifacts = output / "artifacts"
                command = [PYTHON, code / "worker.py", variant, source, manifest_path, output]
            command_row, stdout, stderr = execute(command, env, source, label)
            row = dict(command_row, variant=variant, iteration=iteration)
            if variant != "uv":
                row.update(json.loads(next(line.removeprefix("TIMING_JSON=")
                    for line in stderr.splitlines() if line.startswith("TIMING_JSON="))))
            actual = run.members(artifacts)
            row["validation"] = run.validate(expected, actual)
            row["wheel_exec_match"] = wheel_exec(artifacts) == expected_exec
            assert row["wheel_exec_match"]
            if variant != "uv":
                assert row["validation"]["strict_pass"], row["validation"]
            row["archive_bytes"] = sum(p.stat().st_size for p in artifacts.iterdir())
            (HERE / f"{label}-manifest.json").write_text(json.dumps(actual, indent=2))
            receipt["trials"].append(row)
            save()
    profile_output = WORK / "outputs" / "profile-sdist-only"
    profile_output.mkdir()
    _, stdout, stderr = execute([PYTHON, code / "worker.py", "profile", source, manifest_path,
                                 profile_output], env, source, "profile-sdist-only")
    receipt["profile"] = json.loads(next(line.removeprefix("PROFILE_JSON=")
        for line in stderr.splitlines() if line.startswith("PROFILE_JSON=")))
    shutil.copyfile(profile_output / "sdist.pstats", HERE / "sdist.pstats")
    receipt["profile"]["excluded_from_clean_trials"] = True
    receipt["summary"] = []
    for variant in ("uv", "full", "selective"):
        rows = [r for r in receipt["trials"] if r["variant"] == variant]
        summary = {"variant": variant, "n": len(rows),
                   "median_wall_seconds": statistics.median(r["full_process_seconds"] for r in rows),
                   "range_seconds": [min(r["full_process_seconds"] for r in rows),
                                     max(r["full_process_seconds"] for r in rows)],
                   "strict_passes": sum(r["validation"]["strict_pass"] for r in rows)}
        if variant != "uv":
            summary["phase_medians"] = {key: statistics.median(r[key] for r in rows)
                for key in ("imports_seconds", "sdist_seconds", "extraction_seconds",
                            "wheel_seconds", "python_cpu_seconds")}
        receipt["summary"].append(summary)
    receipt["status"] = "complete"
    save()
    print(json.dumps(receipt["summary"], indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = repr(exc)
        save()
        raise
