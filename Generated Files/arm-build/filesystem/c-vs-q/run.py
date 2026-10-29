"""Owned, offline, matched-volume workload experiment; never removes workspaces."""
import base64
import csv
import hashlib
import io
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
LAB = HERE.parents[1]
ORIGINAL = LAB / "round-3" / "node-archive"
CANONICAL = LAB / "results" / "local-03-canonical"
MAC = LAB / "results" / "ci-40814588064" / "macos" / "ci" / "artifacts" / "prepare-baseline"
NATIVE = r"C:\Program Files\Python313-arm64\python.exe"
NODE = shutil.which("node")
UV = LAB / "tools" / "uv.exe"
receipt = {"source_commit": "264cbad400c8336057a70b9b6a65bfdb4920321e",
           "commands": [], "preparation": [], "trials": [], "diagnostics": [],
           "timing_boundary": "child spawn through exit; checkout and tool provisioning excluded",
           "scan_attribution": "No scan trace; no Defender/MDE causal attribution.",
           "cache_policy": "warm OS cache, new source/extraction/output/temp/cache directories per trial",
           "cpu_scope": "child Python process_time only; Node CPU not included",
           "reference": str(MAC)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save():
    (HERE / "evidence.json").write_text(json.dumps(receipt, indent=2))


def invoke(command, env=None, cwd=None):
    begin = time.perf_counter()
    result = subprocess.run([str(x) for x in command], env=env, cwd=cwd,
                            capture_output=True)
    row = {"argv": [str(x) for x in command], "cwd": str(cwd) if cwd else None,
           "seconds": time.perf_counter() - begin, "returncode": result.returncode}
    receipt["commands"].append(row)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result, row


def members(directory):
    with tarfile.open(next(directory.glob("*.tar.gz"))) as archive:
        sdist = {m.name: {"sha256": hashlib.sha256(archive.extractfile(m).read()).hexdigest(),
                         "exec": bool(m.mode & 0o111), "mode": m.mode}
                 for m in archive if m.isfile()}
    with zipfile.ZipFile(next(directory.glob("*.whl"))) as archive:
        content = {m.filename: archive.read(m) for m in archive.infolist() if not m.is_dir()}
    record = next(n for n in content if n.endswith(".dist-info/RECORD"))
    seen = set()
    for name, digest, size in csv.reader(io.StringIO(content[record].decode())):
        assert name not in seen and name in content
        seen.add(name)
        if name == record:
            assert digest == size == ""
        else:
            encoded = base64.urlsafe_b64encode(hashlib.sha256(content[name]).digest()).rstrip(b"=").decode()
            assert digest == "sha256=" + encoded and size == str(len(content[name]))
    assert seen == set(content)
    return {"sdist": sdist,
            "wheel": {n: hashlib.sha256(data).hexdigest() for n, data in content.items()}}


def validate(expected, actual):
    differences = []
    for kind in expected:
        if expected[kind].keys() != actual[kind].keys():
            differences.append({"kind": kind, "member_set": False})
        for name in expected[kind].keys() & actual[kind].keys():
            if expected[kind][name] != actual[kind][name]:
                differences.append({"kind": kind, "name": name,
                                    "expected": expected[kind][name], "actual": actual[kind][name]})
    return {"strict_pass": not differences, "differences": differences,
            "members": {kind: len(values) for kind, values in actual.items()},
            "raw_record_validated": True}


def main():
    resume = "--resume" in sys.argv
    if resume:
        receipt.clear()
        receipt.update(json.loads((HERE / "evidence.json").read_text()))
        receipt["bounded_resume"] = "Stopped after two complete pairs to reserve budget for simpler PDM cell; unfinished checkout retained, never reused."
    assert NODE and Path(NODE).drive.upper() == "C:"
    croot = Path(r"C:\fastapi-arm-build-lab\copilot-2a73e36a")
    if not resume:
        assert not croot.exists(), "Refuse to reuse an existing owned workspace"
        croot.mkdir(parents=True)
    qroot = HERE / "work" / "copilot-2a73e36a"
    if not resume:
        assert not qroot.exists()
        qroot.mkdir(parents=True)
    roots = {"C": croot, "Q": qroot}
    receipt["node"] = NODE
    receipt["roots"] = {k: str(v) for k, v in roots.items()}
    receipt["original_code_sha256"] = {n: sha(ORIGINAL / n)
                                        for n in ("experiment.py", "writer.cjs", "selective_inputs.py")}
    receipt["source_manifest_sha256"] = sha(CANONICAL / "source-manifest.json")
    assert receipt["source_manifest_sha256"] == "943fd9bf0a02d0dfcc85faf7d3561adcd13b04a40578c301e3b3fdeb0b40f73e"
    expected = members(MAC)
    manifest = json.loads((CANONICAL / "source-manifest.json").read_text())
    receipt["source_inventory_files"] = len(manifest)
    for volume, root in ([] if resume else roots.items()):
        begin = time.perf_counter()
        code = root / "code"
        code.mkdir()
        for name in ("writer.cjs", "selective_inputs.py"):
            shutil.copyfile(ORIGINAL / name, code / name)
        shutil.copyfile(HERE / "baseline.py", code / "baseline.py")
        original = (ORIGINAL / "experiment.py").read_text()
        patched = original.replace("import json\n", "import json\nimport os\n", 1)
        patched = patched.replace('INPUT = LAB / "results" / "local-03-canonical"',
                                  'INPUT = Path(os.environ["LAB_INPUT"])')
        patched = patched.replace('WORK = HERE / "work"', 'WORK = Path(os.environ["LAB_WORK"])')
        patched = patched.replace('SOURCE = WORK / "source"', 'SOURCE = Path(os.environ["LAB_SOURCE"])')
        patched = patched.replace("    start = time.perf_counter()\n    import tarfile",
                                  "    start = time.perf_counter()\n    cpu = time.process_time()\n    import tarfile")
        patched = patched.replace('row = {"label": label,', 'row = {"python_cpu_seconds": time.process_time() - cpu, "label": label,')
        (code / "experiment.py").write_text(patched)
        inputs = root / "inputs"
        inputs.mkdir()
        for name in ("source-manifest.json", "source.tar"):
            shutil.copyfile(CANONICAL / name, inputs / name)
        shutil.copyfile(LAB / "tooling.lock", root / "tooling.lock")
        shutil.copytree(LAB / "wheelhouse" / "ci-40814042898", root / "wheelhouse")
        cache = root / "provision-cache"
        env = os.environ.copy()
        env.update(UV_CACHE_DIR=str(cache), TEMP=str(root), TMP=str(root))
        invoke([UV, "venv", "--python", NATIVE, root / "env"], env)
        python = root / "env" / "Scripts" / "python.exe"
        invoke([UV, "pip", "sync", "--python", python, "--offline", "--no-index",
                "--find-links", root / "wheelhouse", "--require-hashes", root / "tooling.lock"], env)
        runtime, _ = invoke([python, "-c", "import platform,sys,sysconfig,importlib.metadata as m,json; print(json.dumps({'python':sys.version,'base':sys.base_prefix,'platform':sysconfig.get_platform(),'pdm':m.version('pdm-backend')}))"])
        receipt["preparation"].append({"volume": volume, "seconds": time.perf_counter() - begin,
                                       "runtime": json.loads(runtime.stdout),
                                       "driver_sha256": sha(code / "experiment.py"),
                                       "tooling_lock_sha256": sha(root / "tooling.lock")})
        save()

    def trial(volume, algorithm, number, diagnostic=False):
        root = roots[volume]
        label = f"{algorithm}-{number}" + ("-diagnostic" if diagnostic else "")
        if resume:
            label += "-resume"
        run = root / "runs" / label
        run.mkdir(parents=True)
        source = run / "source"
        source.mkdir()
        begin = time.perf_counter()
        with tarfile.open(root / "inputs" / "source.tar") as archive:
            archive.extractall(source, filter="data")
        for name, info in manifest.items():
            assert sha(source / name) == info["sha256"], name
        preparation = time.perf_counter() - begin
        for name in ("temp", "cache", "outputs"):
            (run / name).mkdir()
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("UV_", "PIP_")) and k not in ("PYTHONPATH", "PYTHONHOME")}
        env.update(TEMP=str(run / "temp"), TMP=str(run / "temp"),
                   XDG_CACHE_HOME=str(run / "cache"), LOCALAPPDATA=str(run / "cache"),
                   PDM_CACHE_DIR=str(run / "cache"), PYTHONNOUSERSITE="1",
                   PYTHONDONTWRITEBYTECODE="1", LAB_SOURCE=str(source),
                   LAB_INPUT=str(root / "inputs"), LAB_WORK=str(run / "outputs"))
        env.pop("PDM_BUILD_NO_CLEAN", None)
        if diagnostic:
            env["LAB_AUDIT"] = "1"
        python = root / "env" / "Scripts" / "python.exe"
        script = root / "code" / ("baseline.py" if algorithm == "pdm" else "experiment.py")
        command = [python, script, label] if algorithm == "pdm" else [
            python, script, "--child", label, "4", str(int(diagnostic)), NODE]
        result, command_row = invoke(command, env, source)
        (HERE / f"{volume}-{label}.stdout.log").write_bytes(result.stdout)
        (HERE / f"{volume}-{label}.stderr.log").write_bytes(result.stderr)
        timing_path = root / "code" / f"{label}-timings.json"
        row = json.loads(timing_path.read_text())
        shutil.copyfile(timing_path, HERE / f"{volume}-{label}-timings.json")
        artifact_dir = run / "outputs" / label / "artifacts"
        actual = members(artifact_dir)
        validation = validate(expected, actual)
        (HERE / f"{volume}-{label}-manifest.json").write_text(json.dumps(actual, indent=2))
        row.update(volume=volume, algorithm=algorithm, trial=number,
                   diagnostic=diagnostic, full_process_seconds=command_row["seconds"],
                   source_preparation_seconds=preparation, validation=validation,
                   archive_writes=2,
                   archive_bytes=sum(p.stat().st_size for p in artifact_dir.iterdir()))
        if algorithm == "node":
            selection_path = root / "code" / f"{label}-selection.json"
            selection = json.loads(selection_path.read_text())
            shutil.copyfile(selection_path, HERE / f"{volume}-{label}-selection.json")
            row.update(extracted_files=selection["selected_files"],
                       archive_files=selection["archive_files"],
                       selected_source_payload_reads=selection["archive_files"] - 1)
            assert validation["strict_pass"], validation
        (receipt["diagnostics"] if diagnostic else receipt["trials"]).append(row)
        save()

    for number in (range(3, 4) if resume else range(1, 6)):
        volumes = ["C", "Q"] if number % 2 else ["Q", "C"]
        algorithms = ["pdm", "node"] if number % 2 else ["node", "pdm"]
        for volume in volumes:
            for algorithm in algorithms:
                trial(volume, algorithm, number)
    if "--bounded" not in sys.argv:
        for volume in roots:
            trial(volume, "pdm", 1, True)
            trial(volume, "node", 1, True)
    receipt["summary"] = []
    for volume in roots:
        for algorithm in ("pdm", "node"):
            rows = [r for r in receipt["trials"] if r["volume"] == volume and r["algorithm"] == algorithm]
            receipt["summary"].append({"volume": volume, "algorithm": algorithm, "n": len(rows),
                "median_wall_seconds": statistics.median(r["full_process_seconds"] for r in rows),
                "min_wall_seconds": min(r["full_process_seconds"] for r in rows),
                "max_wall_seconds": max(r["full_process_seconds"] for r in rows),
                "median_python_cpu_seconds": statistics.median(r["python_cpu_seconds"] for r in rows),
                "median_archive_bytes": statistics.median(r["archive_bytes"] for r in rows),
                "extracted_files": rows[0]["extracted_files"],
                "strict_passes": sum(r["validation"]["strict_pass"] for r in rows)})
    receipt["status"] = "complete"
    save()
    print(json.dumps(receipt["summary"], indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        receipt["error"] = repr(exc)
        save()
        raise
