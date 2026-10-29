"""C-only measured children; Q is a controller and post-timing evidence sink."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tarfile
import time

from validate import sha, inventory, compare

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:\fastapi-arm-build-lab\stdlib-ops-2a73e36a")
OLD = ROOT.parent / "copilot-2a73e36a"
LAB = HERE.parents[1]
UV = LAB / "tools" / "uv.exe"
REFERENCE = LAB / "results" / "ci-40814588064" / "macos" / "ci" / "artifacts" / "prepare-baseline"
receipt = dict(status="preparing", commands=[], trials=[], diagnostics=[])


def save():
    (HERE / "evidence.json").write_text(json.dumps(receipt, indent=2))


def execute(command, env, cwd):
    begin = time.perf_counter()
    result = subprocess.run([str(x) for x in command], env=env, cwd=cwd,
                            capture_output=True)
    row = dict(argv=[str(x) for x in command], cwd=str(cwd),
               wall_seconds=time.perf_counter()-begin, returncode=result.returncode)
    receipt["commands"].append(row)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-6000:])
    return result, row


def main():
    begin = time.perf_counter()
    assert not ROOT.exists(), "Fresh owned child required; do not overwrite"
    ROOT.mkdir()
    for name in ("code", "inputs", "outputs", "temp", "cache"):
        (ROOT / name).mkdir()
    for name in ("ops.py", "selector.py", "worker.py", "test_ops.py"):
        shutil.copyfile(HERE / name, ROOT / "code" / name)
    shutil.copyfile(UV, ROOT / "code" / "uv.exe")
    for name in ("source.tar", "source-manifest.json"):
        shutil.copyfile(OLD / "inputs" / name, ROOT / "inputs" / name)
    shutil.copyfile(OLD / "tooling.lock", ROOT / "tooling.lock")
    shutil.copytree(OLD / "wheelhouse", ROOT / "wheelhouse")
    shutil.copytree(REFERENCE, ROOT / "reference")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("UV_", "PIP_")) and k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(TEMP=str(ROOT / "temp"), TMP=str(ROOT / "temp"),
               LOCALAPPDATA=str(ROOT / "cache"), XDG_CACHE_HOME=str(ROOT / "cache"),
               PDM_CACHE_DIR=str(ROOT / "cache"), UV_CACHE_DIR=str(ROOT / "cache"),
               PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PDM_BUILD_NO_CLEAN", None)
    uv = ROOT / "code" / "uv.exe"
    result, _ = execute([uv, "python", "find", "--managed-python", "3.13.15"], env, ROOT)
    base = Path(result.stdout.decode().strip())
    execute([uv, "venv", "--python", base, ROOT / "env"], env, ROOT)
    python = ROOT / "env" / "Scripts" / "python.exe"
    execute([uv, "pip", "sync", "--python", python, "--offline", "--no-index",
             "--find-links", ROOT / "wheelhouse", "--require-hashes", ROOT / "tooling.lock"], env, ROOT)
    result, _ = execute([python, "-c",
        "import sys,sysconfig,platform,importlib.metadata as m,json; print(json.dumps(dict(version=sys.version,base=sys.base_prefix,platform=sysconfig.get_platform(),machine=platform.machine(),pdm=m.version('pdm-backend'))))"], env, ROOT)
    receipt.update(runtime=json.loads(result.stdout), base_exe=str(base),
                   base_exe_sha256=sha(base), venv_exe_sha256=sha(python),
                   python_dll_sha256=sha(base.parent / "python313.dll"),
                   lock_sha256=sha(ROOT / "tooling.lock"),
                   code_hashes={p.name: sha(p) for p in (ROOT / "code").glob("*.py")},
                   bootstrap_seconds=time.perf_counter()-begin,
                   controlled_environment={k: env[k] for k in ("TEMP", "TMP", "LOCALAPPDATA",
                     "XDG_CACHE_HOME", "PDM_CACHE_DIR", "UV_CACHE_DIR",
                     "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE")})
    begin = time.perf_counter()
    source = ROOT / "source"
    source.mkdir()
    with tarfile.open(ROOT / "inputs" / "source.tar") as archive:
        archive.extractall(source, filter="data")
    manifest = ROOT / "inputs" / "source-manifest.json"
    modes = json.loads(manifest.read_text())
    for name, info in modes.items():
        assert sha(source / name) == info["sha256"]
    receipt.update(source_preparation_seconds=time.perf_counter()-begin,
                   source_files=len(modes), source_commit="264cbad400c8336057a70b9b6a65bfdb4920321e",
                   manifest_sha256=sha(manifest))
    result, _ = execute([python, ROOT / "code" / "test_ops.py"], env, ROOT / "code")
    (HERE / "tests.log").write_bytes(result.stdout + result.stderr)
    expected = inventory(ROOT / "reference")
    (HERE / "reference-manifest.json").write_text(json.dumps(expected, indent=2))
    receipt["status"] = "running"
    save()

    def trial(label, variant, diagnostic=False):
        output = ROOT / "outputs" / label
        output.mkdir()
        childenv = dict(env)
        if diagnostic:
            childenv["LAB_AUDIT"] = "1"
        result, command = execute([python, ROOT / "code" / "worker.py", variant,
                                   source, manifest, output], childenv, source)
        # All Q writes and archive validation happen after the process timer stops.
        (HERE / f"{label}.stderr.log").write_bytes(result.stderr)
        (HERE / f"{label}.stdout.log").write_bytes(result.stdout)
        row = json.loads(next(line.removeprefix("TIMING_JSON=")
              for line in result.stderr.decode().splitlines() if line.startswith("TIMING_JSON=")))
        actual = inventory(output / "artifacts")
        row.update(label=label, wall_seconds=command["wall_seconds"],
                   validation=compare(expected, actual), diagnostic=diagnostic)
        (HERE / f"{label}-manifest.json").write_text(json.dumps(actual, indent=2))
        receipt["diagnostics" if diagnostic else "trials"].append(row)
        save()
        if not row["validation"]["strict_pass"]:
            raise RuntimeError(f"Reject {variant}: {row['validation']}")

    # One unmeasured process warms source/tools/OS cache, with fresh metadata/output.
    trial("warmup", "seq-attrs", True)
    receipt["diagnostics"][-1]["warmup"] = True
    orders = [("seq-attrs", "seq-noattrs", "thread-attrs", "thread-noattrs"),
              ("thread-noattrs", "thread-attrs", "seq-noattrs", "seq-attrs"),
              ("thread-attrs", "thread-noattrs", "seq-attrs", "seq-noattrs")]
    for number, order in enumerate(orders, 1):
        for variant in order:
            trial(f"{number}-{variant}", variant)
    for variant in orders[0]:
        trial(f"audit-{variant}", variant, True)
    receipt["summary"] = []
    for variant in orders[0]:
        rows = [r for r in receipt["trials"] if r["variant"] == variant]
        receipt["summary"].append(dict(variant=variant, n=len(rows),
            samples=[r["wall_seconds"] for r in rows],
            medians={k: statistics.median(r[k] for r in rows) for k in
                     ("wall_seconds", "imports_seconds", "sdist_seconds",
                      "extraction_seconds", "wheel_seconds", "python_cpu_seconds")}))
    receipt["status"] = "complete"
    save()
    print(json.dumps(receipt["summary"], indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        receipt.update(status="failed", error=repr(exc))
        save()
        raise
