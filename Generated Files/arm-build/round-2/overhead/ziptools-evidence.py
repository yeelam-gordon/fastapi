"""Persist untimed import/provenance checks after the bounded measurement."""
import ast
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
RUN = HERE / "ziptools-run"
NATIVE = r"C:\Program Files\Python313-arm64\python.exe"
report = json.loads((RUN / "report.json").read_text())
wheel = Path(report["provision"]["source_wheel"])
with zipfile.ZipFile(wheel) as original:
    members = {n: original.read(n) for n in original.namelist()}
    for name in ("tool-source.zip", "tool-bytecode.zip"):
        with zipfile.ZipFile(RUN / name) as tool:
            assert all(tool.read(n) == data for n, data in members.items())
installed = BASE / "tools" / "official-tool-environment" / "Lib" / "site-packages"
assert all((installed / n).read_bytes() == data for n, data in members.items()
           if n.startswith("pdm/") and n.endswith(".py"))
assert len(report["trials"]) == 18
assert all(t["equivalent"] and sorted(t["coverage"].values()) == [65, 1269]
           for t in report["trials"])
assert all(t["tool"]["no_site"] for t in report["trials"]
           if t["variant"] != "installed")
assert all(t["tool"]["backend_file"].endswith(".pyc") for t in report["trials"]
           if t["variant"] == "bytecodezip")
ast.parse((HERE / "ziptools.py").read_text())
probe = [
    NATIVE, "-S", "-c",
    f"import sys; sys.path.insert(0,{str(wheel)!r}); import pdm.backend",
]
result = subprocess.run(probe, capture_output=True, text=True)
assert result.returncode != 0 and "No module named 'pdm'" in result.stderr
(RUN / "unmodified-wheel-probe.stdout.txt").write_text(result.stdout)
(RUN / "unmodified-wheel-probe.stderr.txt").write_text(result.stderr)
evidence = {
    "script_sha256": hashlib.sha256((HERE / "ziptools.py").read_bytes()).hexdigest(),
    "source_and_metadata_members_unchanged": len(members),
    "installed_python_sources_match_official_wheel": True,
    "bytecode_actually_imported": True, "all_artifacts_equivalent": True,
    "unmodified_wheel_probe": {"argv": probe, "returncode": result.returncode},
    "phase_medians": {}, "importtime_cumulative_microseconds": {},
}
for variant in ("installed", "sourcezip", "bytecodezip"):
    trials = [t for t in report["trials"] if t["variant"] == variant and t["measured"]]
    evidence["phase_medians"][variant] = {
        "imports_wall": statistics.median(t["tool"]["imports_wall"] for t in trials),
        **{phase: {kind: statistics.median(t["phases"][phase][kind] for t in trials)
                   for kind in ("wall", "python_cpu")}
           for phase in trials[0]["phases"]},
    }
    evidence["importtime_cumulative_microseconds"][variant] = {
        line.split("|")[-1].strip(): int(line.split("|")[1].strip())
        for line in (RUN / f"{variant}-importtime.txt").read_text().splitlines()
        if line.startswith("import time:") and "|" in line
        and line.split("|")[-1].strip() in {
            "pdm.backend", "pdm.backend.base", "pdm.backend.sdist",
            "pdm.backend.wheel", "importlib.metadata",
        }
    }
evidence["paired_bytecode_savings_seconds"] = [
    next(t["wall_seconds"] for t in report["trials"]
         if t["variant"] == "installed" and t["iteration"] == i)
    - next(t["wall_seconds"] for t in report["trials"]
           if t["variant"] == "bytecodezip" and t["iteration"] == i)
    for i in range(1, 6)
]
(RUN / "verification.json").write_text(json.dumps(evidence, indent=2))
print(json.dumps(evidence, indent=2))
