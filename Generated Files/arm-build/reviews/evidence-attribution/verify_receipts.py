"""Reconcile retained public receipts only; never execute measured workloads."""

import hashlib
import json
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
inputs = {}


def load(relative):
    path = ROOT / relative
    data = path.read_bytes()
    inputs[relative] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


stdlib = load("filesystem/stdlib-ops/evidence.json")
reference = load("filesystem/stdlib-ops/reference-manifest.json")
assert len(stdlib["trials"]) == 12
medians = {}
for variant in ("seq-attrs", "seq-noattrs", "thread-attrs", "thread-noattrs"):
    trials = [t for t in stdlib["trials"] if t["variant"] == variant]
    assert len(trials) == 3
    for trial in trials:
        assert trial["validation"] == {"strict_pass": True, "differences": []}
        assert load(f"filesystem/stdlib-ops/{trial['label']}-manifest.json") == reference
    medians[variant] = statistics.median(t["wall_seconds"] for t in trials)
    summary = next(s for s in stdlib["summary"] if s["variant"] == variant)
    assert medians[variant] == summary["medians"]["wall_seconds"]
for trial in stdlib["diagnostics"]:
    audit = trial["audit"]
    assert sum(v for k, v in audit.items() if k.endswith(":open")) == 1617
    if "noattrs" in trial["variant"]:
        assert audit.get("extract:os.chmod", 0) == 0
        assert audit.get("extract:os.utime", 0) == 0
    else:
        assert audit["extract:os.chmod"] == audit["extract:os.utime"] == 64

frontends = load("frontends/evidence-c87512b2b70d/results.json")
frontend_reference = load("frontends/evidence-c87512b2b70d/canonical-windows-reference.json")
frontend_medians = {}
assert len(frontends["trials"]) == 9
for frontend in "ABC":
    trials = [t for t in frontends["trials"] if t["frontend"] == frontend]
    assert len(trials) == 3
    frontend_medians[frontend] = statistics.median(t["wall_seconds"] for t in trials)
    assert frontend_medians[frontend] == frontends["summary"][frontend]["median_wall_seconds"]
    for trial in trials:
        assert trial["returncode"] == 0 and trial["windows_validation"] == "passed"
        assert len(trial["mac_differences"]) == 5
        manifest = load(f"frontends/evidence-c87512b2b70d/{trial['label']}.manifest.json")
        for key in ("manifest", "modes"):
            assert manifest[key] == frontend_reference[key]

followup = load("filesystem/c-vs-q/followup/evidence.json")
followup_medians = {}
for variant in ("uv", "full", "selective"):
    trials = [t for t in followup["trials"] if t["variant"] == variant]
    assert len(trials) == 3
    followup_medians[variant] = statistics.median(t["full_process_seconds"] for t in trials)
    assert all(t["returncode"] == 0 for t in trials)
    assert all(t["validation"]["strict_pass"] == (variant != "uv") for t in trials)

ci = {}
for run in ("40814042898", "40814588064"):
    jobs = load(f"results/ci-{run}/jobs.json")
    ci[run] = {j["name"]: j["conclusion"] for j in jobs}
assert ci["40814042898"]["macos-15"] == "failure"
assert ci["40814042898"]["windows-11-arm"] == "success"
assert set(ci["40814588064"].values()) == {"success"}
comparison = load("results/ci-40814588064/comparison-r2.json")
assert comparison["status"] == "failed"

print(json.dumps({
    "status": "passed",
    "scope": "retained metadata, manifests and arithmetic; no benchmark or archive re-execution",
    "review_base": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "stdlib_medians_seconds": medians,
    "stdlib_combined_reduction_percent": 100 * (1 - medians["thread-noattrs"] / medians["seq-attrs"]),
    "stdlib_process_cpu_medians_seconds": {
        v: statistics.median(t["python_cpu_seconds"] for t in stdlib["trials"] if t["variant"] == v)
        for v in medians
    },
    "frontend_medians_seconds": frontend_medians,
    "frontend_C_reduction_from_A_percent": 100 * (1 - frontend_medians["C"] / frontend_medians["A"]),
    "followup_medians_seconds": followup_medians,
    "retained_ci_conclusions": ci,
    "strict_ci_comparison": comparison["status"],
    "input_sha256": inputs,
}, indent=2))
