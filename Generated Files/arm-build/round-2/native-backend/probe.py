"""Disposable uv_build proof. Never changes canonical inputs or the validator."""
import ast
import difflib
import email.policy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import sysconfig
import tarfile
import time
import zipfile
from email.parser import BytesParser

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
SOURCE = BASE / "results" / "local-03-canonical" / "source"
REF = BASE / "results" / "local-03-canonical" / "artifacts" / "repeat-01-candidate"
SNAP = HERE / "snapshots" / "source"
RAW = HERE / "rawreports" / "standard"
UV = BASE / "tools" / "uv.exe"
RAW.mkdir(parents=True, exist_ok=True)
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("validator", BASE / "benchmark.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
original = (SOURCE / "pyproject.toml").read_text(encoding="utf-8")
if not SNAP.exists():
    shutil.copytree(SOURCE, SNAP)
env = {k: v for k, v in os.environ.items()
       if not k.startswith(("UV_", "PIP_")) and k not in ("PYTHONPATH", "PYTHONHOME")}
env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
env["TEMP"] = env["TMP"] = str(HERE / "scratch")
Path(env["TEMP"]).mkdir(exist_ok=True)
base_config = original.replace('requires = ["pdm-backend"]',
                               'requires = ["uv_build==0.13.6"]').replace(
    'build-backend = "pdm.backend"', 'build-backend = "uv_build"')
base_config += '''
[tool.uv.build-backend]
module-root = ""
module-name = "fastapi"
source-include = ["tests/**", "docs_src/**", "scripts/**", "docs/en/docs/img/favicon.png"]
'''
report = {
    "python": sys.version, "machine": platform.machine(),
    "platform": sysconfig.get_platform(), "uv": subprocess.check_output(
        [str(UV), "--version"], text=True).strip(),
    "reference": str(REF), "source": str(SOURCE),
    "canonical_pyproject_sha256": hashlib.sha256(
        (SOURCE / "pyproject.toml").read_bytes()).hexdigest(),
    "policy": "Fresh output/cache per trial; offline; default uv build makes sdist then wheel from sdist. "
              "Timed AST version resolution and pyproject regeneration included. "
              "Source copying and validation excluded, like canonical harness. "
              "Static version is incompatible source-metadata change, not accepted optimization.",
    "trials": [],
}


def build(label, config, started=None):
    start = time.perf_counter() if started is None else started
    (SNAP / "pyproject.toml").write_text(config, encoding="utf-8", newline="\n")
    out = RAW / label
    assert not out.exists(), "Use a fresh owned output directory for a rerun"
    command = [str(UV), "build", str(SNAP), "--out-dir", str(out), "--offline",
               "--no-config", "--no-create-gitignore", "--no-python-downloads",
               "--python", sys.executable, "--cache-dir", str(HERE / "cache-standard" / label)]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    elapsed = time.perf_counter() - start
    (RAW / (label + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
    (RAW / (label + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
    row = {"label": label, "command": command, "returncode": result.returncode,
           "wall_seconds_including_metadata": elapsed}
    report["trials"].append(row)
    return out, result.returncode


def contents(path):
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return {i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()}
    with tarfile.open(path) as archive:
        return {i.name.split("/", 1)[1]: archive.extractfile(i).read()
                for i in archive if i.isfile()}


reference = validator.artifact_manifest(REF)
_, dynamic_status = build("dynamic-failure", base_config)
report["dynamic_returncode"] = dynamic_status
for index in range(1, 6):
    start = time.perf_counter()
    tree = ast.parse((SNAP / "fastapi" / "__init__.py").read_text(encoding="utf-8"))
    versions = [ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)]
    assert len(versions) == 1 and isinstance(versions[0], str)
    config = base_config.replace('dynamic = ["version"]', f'version = "{versions[0]}"')
    out, status = build(f"static-{index:02}", config, start)
    if status:
        break
    candidate = validator.artifact_manifest(out)
    differences = {}
    for artifact, expected in reference.items():
        actual = candidate[artifact]
        changed = sorted(k for k in expected.keys() & actual.keys() if expected[k] != actual[k])
        differences[artifact] = {"missing": sorted(expected.keys() - actual.keys()),
                                 "extra": sorted(actual.keys() - expected.keys()),
                                 "changed": changed}
        before, after = contents(REF / artifact), contents(out / artifact)
        texts = {}
        for member in changed:
            if member.endswith(("METADATA", "PKG-INFO", "WHEEL", "entry_points.txt", "pyproject.toml")):
                texts[member] = "".join(difflib.unified_diff(
                    before[member].decode().splitlines(True), after[member].decode().splitlines(True),
                    fromfile="PDM/" + member, tofile="uv/" + member))
        differences[artifact]["text_diffs"] = texts
        meta = next(k for k in before if k.endswith(("METADATA", "PKG-INFO")))
        parser = BytesParser(policy=email.policy.default)
        left, right = parser.parsebytes(before[meta]), parser.parsebytes(after[meta])
        fields = sorted(set(left.keys()) | set(right.keys()))
        differences[artifact]["metadata_field_differences"] = {
            k: {"PDM": left.get_all(k), "uv": right.get_all(k)}
            for k in fields if left.get_all(k) != right.get_all(k)}
        differences[artifact]["metadata_body_equal"] = left.get_payload() == right.get_payload()
        differences[artifact]["member_counts"] = {"PDM": len(expected), "uv": len(actual)}
    report["trials"][-1]["strict_equivalent"] = candidate == reference
    report["trials"][-1]["differences"] = differences
    (RAW / f"static-{index:02}.manifest.json").write_text(
        json.dumps(candidate, indent=2), encoding="utf-8")
    print(index, report["trials"][-1]["wall_seconds_including_metadata"],
          report["trials"][-1]["strict_equivalent"], flush=True)
successful = [r["wall_seconds_including_metadata"] for r in report["trials"]
              if r["label"].startswith("static") and r["returncode"] == 0]
if successful:
    report["static_median_seconds"] = statistics.median(successful)
    report["static_range_seconds"] = [min(successful), max(successful)]
report["strict_goal_achieved"] = False
report["canonical_pyproject_unchanged"] = report["canonical_pyproject_sha256"] == hashlib.sha256(
    (SOURCE / "pyproject.toml").read_bytes()).hexdigest()
(RAW / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
(HERE / "snapshots" / "pyproject.diff").write_text("".join(difflib.unified_diff(
    original.splitlines(True), (SNAP / "pyproject.toml").read_text(
        encoding="utf-8").splitlines(True), fromfile="canonical", tofile="disposable-static")),
    encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "trials"}, indent=2))
