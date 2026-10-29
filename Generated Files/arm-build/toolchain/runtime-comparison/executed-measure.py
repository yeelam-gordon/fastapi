"""Offline distribution A/B, not a PGO causal experiment. Never installs Python."""

import argparse
import hashlib
import importlib.util
import io
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
import zipfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pe(path):
    with Path(path).open("rb") as stream:
        stream.seek(0x3C)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset)
        assert stream.read(4) == b"PE\0\0"
        machine = struct.unpack("<H", stream.read(2))[0]
    assert machine == 0xAA64, (path, machine)
    return hex(machine)


def modes(directory):
    result = {}
    for path in directory.iterdir():
        if path.name.endswith(".whl"):
            with zipfile.ZipFile(path) as archive:
                result[path.name] = {
                    item.filename: (item.external_attr >> 16) & 0xFFFF
                    for item in archive.infolist()
                }
        else:
            with tarfile.open(path) as archive:
                result[path.name] = {item.name: item.mode for item in archive}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    root, master = args.root, args.master
    root.mkdir(exist_ok=True, parents=True)
    assert {path.name for path in root.iterdir()} <= {"launch"}
    for name in ("code", "tools", "wheelhouse", "inputs", "source", "outputs",
                 "temp", "cache", "evidence", "reference", "mac-reference"):
        (root / name).mkdir()
    shutil.copy2(__file__, root / "code" / "measure.py")
    report = {"status": "preparing", "root": str(root), "commands": [], "trials": []}
    evidence = root / "evidence"

    def save():
        text = json.dumps(report, indent=2)
        text = text.replace(str(Path.home()).replace("\\", "\\\\"),
                            "<USERPROFILE>")
        (evidence / "results.json").write_text(text, encoding="utf-8")

    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PIP_", "UV_", "PYTHON"))}
    env.update(TEMP=str(root / "temp"), TMP=str(root / "temp"),
               PYTHONNOUSERSITE="1", PIP_CONFIG_FILE=os.devnull,
               PIP_NO_INDEX="1", PIP_FIND_LINKS=str(root / "wheelhouse"),
               UV_NO_INDEX="1", UV_FIND_LINKS=str(root / "wheelhouse"),
               UV_OFFLINE="1", UV_NO_CONFIG="1", UV_PYTHON_DOWNLOADS="never")
    uv = root / "tools" / "uv.exe"
    shutil.copy2(master / "tools" / "uv.exe", uv)
    report["uv_sha256"] = sha(uv)
    env["PATH"] = str(uv.parent) + os.pathsep + env["PATH"]
    lock = root / "inputs" / "tooling.lock"
    shutil.copy2(master / "tooling.lock", lock)
    report["tooling_lock_sha256"] = sha(lock)
    wheel_source = master / "wheelhouse" / "ci-40814042898"
    hashes = json.loads((wheel_source / "sha256.json").read_text())
    report["wheels"] = {}
    for wheel in wheel_source.glob("*.whl"):
        assert sha(wheel) == hashes[wheel.name]
        shutil.copy2(wheel, root / "wheelhouse" / wheel.name)
        report["wheels"][wheel.name] = sha(wheel)
    constraints = root / "inputs" / "constraints.txt"
    constraints.write_text("pdm-backend==2.5.0\n", encoding="utf-8")
    env.update(PIP_CONSTRAINT=str(constraints), UV_CONSTRAINT=str(constraints),
               UV_BUILD_CONSTRAINT=str(constraints))
    report["environment"] = {key: value for key, value in env.items()
                             if key.startswith(("PIP_", "UV_", "PYTHON"))
                             or key in ("TEMP", "TMP")}
    source_commit = subprocess.check_output(
        ["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip()
    assert source_commit == "79cab5bed28b24d92c185d236feb33f5783dfeb3"
    raw_archive = root / "inputs" / "source-git.tar"
    subprocess.run(["git", "-C", str(args.source), "archive", "--format=tar",
                    "--output", str(raw_archive), source_commit], check=True)
    archive_path = root / "inputs" / "source.tar"
    normalized = []
    with tarfile.open(raw_archive) as original, tarfile.open(
            archive_path, "w", format=tarfile.PAX_FORMAT,
            pax_headers=original.pax_headers) as canonical:
        for item in original:
            if not item.isfile():
                canonical.addfile(item)
                continue
            data = original.extractfile(item).read()
            if b"\0" not in data:
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError:
                    pass
                else:
                    converted = data.replace(b"\r\n", b"\n")
                    if converted != data:
                        normalized.append(item.name)
                    data = converted
            item.size = len(data)
            canonical.addfile(item, io.BytesIO(data))
    report["source_commit"] = source_commit
    report["source_archive_sha256"] = sha(archive_path)
    report["raw_git_archive_sha256"] = sha(raw_archive)
    report["canonical_lf_members"] = normalized
    with tarfile.open(archive_path) as archive:
        assert archive.pax_headers["comment"] == source_commit
        assert not any("Generated Files" in item.name for item in archive)
        archive.extractall(root / "source", filter="data")
    assert b"\r\n" not in (root / "source" / "pyproject.toml").read_bytes()
    shutil.copy2(master / "benchmark.py", root / "code" / "validator.py")
    spec = importlib.util.spec_from_file_location("validator", root / "code" / "validator.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    reference = Path(r"C:\fastapi-arm-build-lab\frontends-2a73e36a\outputs\prepare-A")
    mac_reference = master / "results" / "ci-40814588064" / "macos" / "ci" / "artifacts" / "prepare-baseline"
    for original, target in ((reference, root / "reference"),
                             (mac_reference, root / "mac-reference")):
        for path in original.iterdir():
            shutil.copy2(path, target / path.name)
    baseline = validator.artifact_manifest(root / "reference")
    baseline_modes = modes(root / "reference")
    mac = validator.artifact_manifest(root / "mac-reference")
    (evidence / "windows-reference.json").write_text(
        json.dumps({"manifest": baseline, "full_modes": baseline_modes}, indent=2))
    report["reference_origin"] = str(reference)
    report["reference_hashes"] = {p.name: sha(p) for p in (root / "reference").iterdir()}

    def run(label, argv, kind=None, runtime=None, measured=False):
        argv = list(map(str, argv))
        row = dict(label=label, argv=argv, runtime=runtime, command=kind,
                   measured=measured, cwd=str(root / "source"))
        report["commands"].append(row)
        save()
        start = time.perf_counter()
        with (evidence / (label + ".stdout.txt")).open("wb") as out, (
                evidence / (label + ".stderr.txt")).open("wb") as err:
            result = subprocess.run(argv, env=env, cwd=root / "source",
                                    stdout=out, stderr=err, timeout=180)
        row.update(wall_seconds=time.perf_counter() - start, returncode=result.returncode)
        # A Windows venv launcher/uv process does not account for descendant CPU.
        row["cpu_seconds"] = None
        row["cpu_scope"] = "Not measured; launcher-only zero is not workload CPU"
        save()
        print(label, round(row["wall_seconds"], 3), result.returncode, flush=True)
        assert result.returncode == 0, label
        return row

    managed = subprocess.check_output(
        [str(uv), "python", "find", "--managed-python", "3.13.15"],
        text=True, env=env).strip()
    runtimes = {"stock": Path(r"C:\Program Files\Python313-arm64\python.exe"),
                "managed": Path(managed)}
    report["runtimes"] = {}
    interpreters = {}
    for name, base in runtimes.items():
        dll = base.parent / "python313.dll"
        report["runtimes"][name] = {
            "base_exe": str(base), "base_exe_sha256": sha(base),
            "base_exe_pe": pe(base), "dll": str(dll),
            "dll_sha256": sha(dll), "dll_pe": pe(dll)}
        versions = subprocess.check_output(
            ["pwsh", "-NoProfile", "-Command",
             f"Get-Item '{base}','{dll}' | ForEach-Object {{ "
             "[PSCustomObject]@{Name=$_.Name; FileVersion=$_.VersionInfo.FileVersion;"
             "ProductVersion=$_.VersionInfo.ProductVersion}} | ConvertTo-Json"],
            text=True)
        report["runtimes"][name]["file_versions"] = json.loads(versions)
        run("inventory-" + name, [base, "-c",
            "import sys,sysconfig,platform,zlib,bz2,lzma,ssl,sqlite3,importlib.util,json;"
            "print(json.dumps(dict(version=sys.version,platform=sysconfig.get_platform(),"
            "machine=platform.machine(),zlib_compile=zlib.ZLIB_VERSION,"
            "zlib_runtime=zlib.ZLIB_RUNTIME_VERSION,openssl=ssl.OPENSSL_VERSION,"
            "sqlite=sqlite3.sqlite_version,"
            "codec_modules={n:importlib.util.find_spec(n).origin "
            "for n in ('zlib','_bz2','_lzma')}),indent=2));"
            "assert sys.version_info[:3]==(3,13,15);"
            "assert sysconfig.get_platform()=='win-arm64'"])
        run("venv-" + name, [uv, "venv", "--python", base,
                            root / ("env-" + name), "--no-project"])
        python = root / ("env-" + name) / "Scripts" / "python.exe"
        interpreters[name] = python
        run("hash-sync-" + name, [uv, "pip", "sync", "--python", python,
                                 "--require-hashes", "--no-index",
                                 "--find-links", root / "wheelhouse", lock])
        run("build-callpath-" + name, [python, "-c",
            "from build.env import _PipBackend;import inspect,importlib.metadata as m;"
            "b=_PipBackend();print({n:m.version(n) for n in ('build','pip','pdm-backend')});"
            "print('valid_outer_pip',b._has_valid_outer_pip,"
            "'virtualenv',b._has_virtualenv,'create_with_virtualenv',b._create_with_virtualenv);"
            "print(inspect.getsource(_PipBackend));"
            "assert b._has_valid_outer_pip and not b._create_with_virtualenv"])
    report["preparation_seconds"] = time.perf_counter() - started

    def pycs(name, kind):
        paths = [root / ("env-" + name), root / "cache" / name / kind]
        return sum(1 for path in paths for p in path.rglob("*.pyc")
                   if "pdm" in str(p).lower())

    def build(name, kind, label, measured=False):
        cell = root / "cache" / name / kind
        cell.mkdir(parents=True, exist_ok=True)
        env.update(UV_CACHE_DIR=str(cell / "uv"), PIP_CACHE_DIR=str(cell / "pip"))
        out = root / "outputs" / label
        out.mkdir()
        python = interpreters[name]
        if kind == "uv":
            argv = [uv, "build", root / "source", "--python", python,
                    "--out-dir", out, "--build-constraints", constraints,
                    "--no-create-gitignore"]
        else:
            argv = [python, "-m", "build", root / "source",
                    "--outdir", out, "--installer", "pip"]
        before = pycs(name, kind)
        row = run(label, argv, kind, name, measured)
        row["pdm_pyc_count_before"] = before
        row["pdm_pyc_count_after"] = pycs(name, kind)
        manifest = validator.artifact_manifest(out)
        full_modes = modes(out)
        validator.compare_manifests(baseline, manifest)
        assert full_modes == baseline_modes
        differences = [
            {"artifact": artifact, "member": member, "mac": mac[artifact].get(member),
             "windows": manifest[artifact].get(member)}
            for artifact in mac
            for member in sorted(set(mac[artifact]) | set(manifest[artifact]))
            if mac[artifact].get(member) != manifest[artifact].get(member)]
        row.update(windows_validation="passed", mac_differences=differences,
                   artifact_sha256={p.name: sha(p) for p in out.iterdir()})
        (evidence / (label + ".manifest.json")).write_text(json.dumps(
            {"manifest": manifest, "full_modes": full_modes}, indent=2))
        if measured:
            report["trials"].append(row)
        save()

    report["status"] = "measuring"
    for kind in ("uv", "pip"):
        for name in runtimes:
            build(name, kind, f"warm-{kind}-{name}")
        for index, order in enumerate((("stock", "managed"), ("managed", "stock"),
                                      ("stock", "managed")), 1):
            if time.perf_counter() - started > 520:
                report["incomplete"] = "Stopped at active-time boundary; no fabricated samples"
                break
            for name in order:
                build(name, kind, f"trial-{kind}-{index}-{name}", True)
    report["summary"] = {}
    for kind in ("uv", "pip"):
        report["summary"][kind] = {}
        for name in runtimes:
            samples = [r["wall_seconds"] for r in report["trials"]
                       if r["command"] == kind and r["runtime"] == name]
            report["summary"][kind][name] = dict(
                samples=samples, median=statistics.median(samples) if samples else None,
                minimum=min(samples) if samples else None,
                maximum=max(samples) if samples else None)
    report.update(status="complete" if not report.get("incomplete") else "incomplete",
                  total_seconds=time.perf_counter() - started,
                  harness_sha256=sha(__file__))
    save()
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
