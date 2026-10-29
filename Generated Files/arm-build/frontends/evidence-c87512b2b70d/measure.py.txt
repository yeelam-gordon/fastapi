"""Bounded, offline standard frontend comparison; no packaging implementation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
BASE_PYTHON = Path(r"C:\Program Files\Python313-arm64\python.exe")
COMMIT = "264cbad400c8336057a70b9b6a65bfdb4920321e"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.perf_counter()
    root = Path(r"C:\fastapi-arm-build-lab\frontends-2a73e36a")
    if root.exists():
        root /= uuid.uuid4().hex[:12]
    root.mkdir(parents=True, exist_ok=False)
    evidence = HERE / ("evidence-" + root.name)
    evidence.mkdir(exist_ok=False)
    report = {"workspace": str(root), "commit": COMMIT, "commands": [], "trials": []}

    def save():
        (evidence / "results.json").write_text(json.dumps(report, indent=2))

    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PIP_", "UV_")) and
           k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONDONTWRITEBYTECODE")}
    for folder in ("tools", "wheelhouse", "cache", "temp", "source", "outputs"):
        (root / folder).mkdir()
    env.update(TEMP=str(root / "temp"), TMP=str(root / "temp"),
               PYTHONNOUSERSITE="1", PIP_CONFIG_FILE=os.devnull,
               PIP_NO_INDEX="1", PIP_FIND_LINKS=str(root / "wheelhouse"),
               PIP_CACHE_DIR=str(root / "cache" / "pip"),
               UV_NO_INDEX="1", UV_FIND_LINKS=str(root / "wheelhouse"),
               UV_CACHE_DIR=str(root / "cache" / "uv"), UV_OFFLINE="1",
               UV_NO_CONFIG="1", UV_PYTHON_DOWNLOADS="never",
               UV_NO_MANAGED_PYTHON="1")
    uv = root / "tools" / "uv.exe"
    original_uv = LAB / "tools" / "uv.exe"
    shutil.copy2(original_uv, uv)
    assert sha(uv) == sha(original_uv)
    report["uv_sha256"] = sha(uv)
    env["PATH"] = str(uv.parent) + os.pathsep + env["PATH"]
    lock = root / "tooling.lock"
    shutil.copy2(LAB / "tooling.lock", lock)
    report["lock_sha256"] = sha(lock)
    wheel_source = LAB / "wheelhouse" / "ci-40814042898"
    hashes = json.loads((wheel_source / "sha256.json").read_text())
    report["wheel_hashes"] = {}
    for path in wheel_source.glob("*.whl"):
        assert sha(path) == hashes[path.name], path
        shutil.copy2(path, root / "wheelhouse" / path.name)
        report["wheel_hashes"][path.name] = hashes[path.name]
    archive_path = root / "source.tar"
    shutil.copy2(Path(r"C:\fastapi-arm-build-lab\copilot-2a73e36a\inputs\source.tar"), archive_path)
    report["archive_sha256"] = sha(archive_path)
    with tarfile.open(archive_path) as archive:
        report["archive_pax"] = archive.pax_headers
        assert archive.pax_headers.get("comment") == COMMIT
        archive.extractall(root / "source", filter="data")
    project = (root / "source" / "pyproject.toml").read_text()
    (evidence / "pyproject.toml.txt").write_text(project)
    constraint = root / "backend-constraints.txt"
    constraint.write_text("pdm-backend==2.5.0\n")
    env["PIP_CONSTRAINT"] = str(constraint)
    env["UV_CONSTRAINT"] = str(constraint)
    env["UV_BUILD_CONSTRAINT"] = str(constraint)
    report["environment"] = {k: v for k, v in env.items()
                             if k.startswith(("PIP_", "UV_", "PYTHON")) or k in ("TEMP", "TMP")}

    def run(label, argv, timed=False, diagnostic=False):
        argv = list(map(str, argv))
        out_path, err_path = evidence / (label + ".stdout.txt"), evidence / (label + ".stderr.txt")
        row = {"label": label, "argv": argv, "cwd": str(root / "source"),
               "timed": timed, "diagnostic": diagnostic}
        report["commands"].append(row)
        save()
        start = time.perf_counter()
        with out_path.open("wb") as out, err_path.open("wb") as err:
            process = subprocess.Popen(argv, cwd=root / "source", env=env, stdout=out, stderr=err)
            # Windows process CPU excludes descendants; explicitly report only this process.
            process.wait(timeout=180)
            import ctypes
            from ctypes import wintypes
            times = [wintypes.FILETIME() for _ in range(4)]
            valid = ctypes.windll.kernel32.GetProcessTimes(
                wintypes.HANDLE(int(process._handle)), *[ctypes.byref(t) for t in times])
            if valid:
                row["parent_only_cpu_seconds"] = sum(
                    (t.dwHighDateTime << 32) + t.dwLowDateTime for t in times[2:]) / 1e7
        row.update(wall_seconds=time.perf_counter() - start, returncode=process.returncode)
        save()
        print(label, round(row["wall_seconds"], 3), process.returncode, flush=True)
        if process.returncode:
            print(err_path.read_text(errors="replace"), flush=True)
            raise RuntimeError(label)
        return out_path.read_text(errors="replace")

    run("uv-version", [uv, "--version"])
    run("venv-provision", [uv, "venv", "--python", BASE_PYTHON, root / "env", "--no-project"])
    python = root / "env" / "Scripts" / "python.exe"
    run("offline-hash-sync", [uv, "pip", "sync", "--python", python, "--require-hashes",
                             "--no-index", "--find-links", root / "wheelhouse", lock])
    build_help = run("build-help", [python, "-m", "build", "--help"])
    uv_help = run("uv-build-help", [uv, "build", "--help"])
    assert "--installer" in build_help and "--outdir" in build_help
    assert all(flag in uv_help for flag in (
        "--build-constraints", "--out-dir", "--no-create-gitignore"))
    run("versions-and-isolation-path", [python, "-c",
        "import sys,sysconfig,importlib.metadata as m,importlib.util; "
        "from build.env import _PipBackend; b=_PipBackend(); "
        "print(sys.version,sysconfig.get_platform()); "
        "print({n:m.version(n) for n in ('build','pip','pdm-backend','packaging','pyproject-hooks')}); "
        "print('valid_outer_pip=',b._has_valid_outer_pip,'virtualenv=',b._has_virtualenv,"
        "'create_with_virtualenv=',b._create_with_virtualenv); "
        "print('ensurepip_used_by_build=',not b._has_valid_outer_pip and not b._create_with_virtualenv)"])
    installed = root / "env" / "Lib" / "site-packages" / "build"
    for name in ("env.py", "__main__.py"):
        shutil.copy2(installed / name, evidence / ("build-1.6.1-" + name + ".txt"))
    shutil.copy2(LAB / "benchmark.py", root / "tools" / "artifact_validation.py")
    sys.path.insert(0, str(root / "tools"))
    import artifact_validation as validator

    references = LAB / "results" / "ci-40814588064"
    win_path = references / "windows" / "ci" / "artifacts" / "prepare-baseline"
    mac_path = references / "macos" / "ci" / "artifacts" / "prepare-baseline"
    historical_windows = validator.artifact_manifest(win_path)
    baseline = None
    mac = validator.artifact_manifest(mac_path)

    def modes(directory):
        result = {}
        for path in directory.iterdir():
            if path.name.endswith(".whl"):
                with zipfile.ZipFile(path) as z:
                    result[path.name] = {i.filename: (i.external_attr >> 16) & 0o7777
                                         for i in z.infolist() if not i.is_dir()}
            elif path.name.endswith(".tar.gz"):
                with tarfile.open(path) as t:
                    result[path.name] = {i.name: i.mode for i in t if i.isfile()}
        return result

    baseline_modes = None
    report["references"] = {"windows": str(win_path), "macos": str(mac_path)}
    (evidence / "windows-reference.json").write_text(json.dumps(
        {"manifest": historical_windows, "modes": modes(win_path)}, indent=2))
    report["preparation_seconds_before_builds"] = time.perf_counter() - started

    def build(kind, label, timed=False, diagnostic=False):
        nonlocal baseline, baseline_modes
        output = root / "outputs" / label
        output.mkdir(exist_ok=False)
        if kind in ("A", "B"):
            argv = [python, "-m", "build", str(root / "source"), "--outdir", output]
            if kind == "B":
                argv += ["--installer", "uv"]
        else:
            argv = [uv, "build", str(root / "source"), "--python", python,
                    "--out-dir", output, "--build-constraints", constraint,
                    "--no-create-gitignore"]
        if diagnostic:
            argv += ["-v"]
        run(label, argv, timed=timed, diagnostic=diagnostic)
        manifest = validator.artifact_manifest(output)
        actual_modes = modes(output)
        if baseline is None:
            assert label == "prepare-A"
            baseline, baseline_modes = manifest, actual_modes
            report["same_os_reference"] = str(output)
            report["historical_windows_reference_status"] = (
                "Not canonical-byte equivalent: historical Windows artifacts contain CRLF; "
                "current Git archive and macOS contain LF. No normalization or waiver applied. "
                "Canonical same-OS reference is this fresh default python -m build preparation.")
            (evidence / "canonical-windows-reference.json").write_text(json.dumps(
                {"manifest": baseline, "modes": baseline_modes}, indent=2))
        validator.compare_manifests(baseline, manifest)
        assert actual_modes == baseline_modes, label + ": full permission modes differ"
        differences = []
        for artifact in mac:
            for name in sorted(set(mac[artifact]) | set(manifest[artifact])):
                if mac[artifact].get(name) != manifest[artifact].get(name):
                    differences.append({"artifact": artifact, "member": name,
                                        "mac": mac[artifact].get(name), "windows": manifest[artifact].get(name)})
        (evidence / (label + ".manifest.json")).write_text(json.dumps(
            {"manifest": manifest, "modes": actual_modes, "mac_differences": differences}, indent=2))
        row = report["commands"][-1]
        row.update(frontend=kind, windows_validation="passed", mac_differences=differences)
        if timed:
            report["trials"].append(row)
        save()

    # One diagnostic preparation per frontend, excluded from measured samples.
    for kind in "ABC":
        build(kind, "prepare-" + kind, diagnostic=True)
    for iteration, order in enumerate(("ABC", "CBA", "ABC"), 1):
        if iteration == 3 and time.perf_counter() - started > 440:
            report["reduction_reason"] = "Third round omitted to retain ~10 minute active bound."
            break
        for kind in order:
            build(kind, f"trial-{iteration}-{kind}", timed=True)
    report["summary"] = {
        kind: {"wall_samples": [r["wall_seconds"] for r in report["trials"] if r["frontend"] == kind],
               "median_wall_seconds": statistics.median(
                   r["wall_seconds"] for r in report["trials"] if r["frontend"] == kind)}
        for kind in "ABC"}
    report["total_seconds"] = time.perf_counter() - started
    save()
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
