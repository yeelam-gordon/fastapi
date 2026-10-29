"""Read-only paired evidence extraction; writes only this owned analysis directory."""
import csv
import hashlib
import json
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = Path(r"Q:\fastapi")
BASE = ROOT / "Generated Files" / "arm-build"
INPUT = BASE / "results" / "ci-40814588064"
used = {}
rows = []


def read(path):
    data = path.read_bytes()
    used[str(path)] = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    return data.decode("utf-8-sig")


def load(path):
    return json.loads(read(path))


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def seconds(a, b):
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()


def pair(tier, name, windows, macos, sources, note=""):
    w, m = list(windows), list(macos)
    wm, mm = statistics.median(w), statistics.median(m)
    rows.append({
        "tier": tier, "phase": name, "windows_seconds": wm,
        "macos_seconds": mm, "windows_minus_macos_seconds": wm - mm,
        "absolute_gap_seconds": abs(wm - mm),
        "windows_over_macos": wm / mm if mm else None,
        "windows_n": len(w), "macos_n": len(m),
        "windows_range": [min(w), max(w)], "macos_range": [min(m), max(m)],
        "windows_samples": w, "macos_samples": m, "sources": sources, "note": note,
    })


reports = {os: load(INPUT / os / "ci" / "report.json") for os in ["windows", "macos"]}
jobs = {j["name"]: j for j in load(INPUT / "jobs.json")}
comparison = load(INPUT / "comparison-r2.json")
run_receipt = load(OUT / "run-api-receipt.json")
for name in ["CI.md", "FINDINGS.md"]:
    read(BASE / name)
for os in reports:
    read(INPUT / os / "ci" / "harness.py")
    read(INPUT / os / "ci" / "build-constraints.txt")
receipts = {
    os: {name: load(INPUT / os / "bootstrap" / f"{name}.json")
         for name in ["python-setup", "provision", "smoke"]}
    for os in reports
}
coverage = {}
for os, report in reports.items():
    coverage[os] = []
    for command in report["commands"]:
        entry = {"phase": command["phase"], "argv": command["argv"], "logs": {}}
        for stream in ["stdout", "stderr"]:
            path = INPUT / os / "ci" / Path(command[stream].replace("/", "\\"))
            text = read(path)
            entry["logs"][stream] = {
                "path": str(path), "bytes": path.stat().st_size,
                "import_rows": len(re.findall(r"^import time:\s*\d+", text, re.M)),
                "markers": [line for line in text.splitlines()
                            if line.startswith(("Building ", "* Building", "* Getting"))],
                "adding_lines": sum(line.startswith(" - Adding ") for line in text.splitlines()),
                "per_line_timestamps": bool(re.search(r"^\d{4}-\d\d-\d\dT", text, re.M)),
            }
        coverage[os].append(entry)
    for path in (INPUT / os / "bootstrap").glob("*.log"):
        read(path)

for variant in ["baseline", "candidate"]:
    samples = {
        os: [c["wall_seconds"] for c in r["commands"]
             if c["phase"].startswith("repeat-") and c["phase"].endswith(variant)]
        for os, r in reports.items()
    }
    pair("normal-full-build", variant, samples["windows"], samples["macos"],
         ["windows\\ci\\report.json#commands", "macos\\ci\\report.json#commands"],
         "Offline warm cache; complete sdist then wheel; artifact parity REJECTED.")
wc = {c["phase"]: c for c in reports["windows"]["commands"]}
mc = {c["phase"]: c for c in reports["macos"]["commands"]}
for name, prefix in [("all-recorded-commands", ""), ("fourteen-measured-builds", "repeat-")]:
    totals = {os: sum(c["wall_seconds"] for c in r["commands"] if c["phase"].startswith(prefix))
              for os, r in reports.items()}
    pair("command-subtotal", name, [totals["windows"]], [totals["macos"]],
         ["windows\\ci\\report.json#commands", "macos\\ci\\report.json#commands"],
         "Sum of disjoint command walls within one job, not a per-build median or CPU attribution.")
for phase in wc.keys() & mc.keys():
    if not phase.startswith("repeat-"):
        pair("command-wall", phase, [wc[phase]["wall_seconds"]], [mc[phase]["wall_seconds"]],
             [f"{os}\\ci\\report.json#commands/{phase}" for os in reports],
             "Diagnostic uses different frontend and instrumentation." if phase.startswith("diagnostic") else "")

excluded = []
for receipt in ["python-setup", "provision", "smoke"]:
    key = "phases" if receipt == "python-setup" else "commands"
    commands = {os: {c["phase"]: c for c in receipts[os][receipt][key]} for os in reports}
    for phase in sorted(commands["windows"].keys() | commands["macos"].keys()):
        if all(phase in commands[os] for os in reports):
            pair("bootstrap-command", phase, [commands["windows"][phase]["seconds"]],
                 [commands["macos"][phase]["seconds"]],
                 [f"{os}\\bootstrap\\{receipt}.json#{phase}" for os in reports])
        else:
            excluded.append({"phase": phase, "reason": "Windows-only; no paired Mac sample",
                             "windows_seconds": commands["windows"][phase]["seconds"]})
    if receipt == "python-setup":
        pair("bootstrap-total", "python-receipt-command-subtotal",
             [sum(c["seconds"] for c in commands["windows"].values())],
             [sum(c["seconds"] for c in commands["macos"].values())],
             [f"{os}\\bootstrap\\{receipt}.json" for os in reports],
             "Sum of disjoint commands, excludes setup wrapper overhead.")

wjob, mjob = jobs["windows-11-arm"], jobs["macos-15"]
pair("scheduling-envelope", "run-created-to-job-start",
     [seconds(run_receipt["created_at"], wjob["started_at"])],
     [seconds(run_receipt["created_at"], mjob["started_at"])],
     ["run-api-receipt.json#created_at", "jobs.json#started_at"],
     "Scheduling envelope only, NOT isolated queue time or VM provisioning; second resolution.")
ws = {s["name"]: s for s in wjob["steps"] if s["conclusion"] == "success"}
ms = {s["name"]: s for s in mjob["steps"] if s["conclusion"] == "success"}
export = receipts["windows"]["provision"]["commands"][-1]["seconds"]
for name in ws.keys() & ms.keys():
    w = seconds(ws[name]["started_at"], ws[name]["completed_at"])
    m = seconds(ms[name]["started_at"], ms[name]["completed_at"])
    note = "Coarse second-resolution API boundary; overlapping tiers, do not add."
    if name == "Provision pinned native tools and offline wheelhouse":
        w -= export
        note += " Windows-only pip wheelhouse download subtracted; wrapper overhead remains."
    pair("workflow-step", name, [w], [m], ["jobs.json#steps/" + name], note)
raw = {os: seconds(j["started_at"], j["completed_at"])
       for os, j in [("windows", wjob), ("macos", mjob)]}
extra_steps = ["Upload Windows ARM offline dependencies", "Preserve shared frozen experiment locks"]
extra = sum(seconds(ws[n]["started_at"], ws[n]["completed_at"]) for n in extra_steps)
pair("job-envelope", "known-extra-excluded-job-envelope", [raw["windows"] - export - extra],
     [raw["macos"]], ["jobs.json", "windows\\bootstrap\\provision.json"],
     "Not a normal build: includes preparation, 14 trials, diagnostics, smoke, upload, cleanup. "
     "Subtract Windows-only wheelhouse download, upload and frozen-lock step; "
     "coarse wrapper residue and scheduler/cleanup tails remain.")

console = read(OUT / "workflow-console.log")
groups = {}
for os, label in [("windows", "windows-11-arm"), ("macos", "macos-15")]:
    stack = []
    groups[os] = {}
    for number, line in enumerate(console.splitlines(), 1):
        if not line.startswith(label + "\t"):
            continue
        match = re.search(r"\d{4}-\d\d-\d\dT[\d:.]+Z", line)
        if not match:
            continue
        if "##[group]" in line:
            stack.append((line.split("##[group]", 1)[1], match[0], number))
        elif "##[endgroup]" in line and stack:
            name, started, first = stack.pop()
            groups[os].setdefault(name, []).append({
                "seconds": seconds(started, match[0]), "lines": [first, number]})
for name in groups["windows"].keys() & groups["macos"].keys():
    if name not in {
        "Getting Git version info", "Determining repository object format",
        "Initializing the repository", "Disabling automatic garbage collection",
        "Setting up auth", "Fetching the repository", "Determining the checkout info",
        "Checking out the ref", "Removing auth",
    }:
        continue
    if len(groups["windows"][name]) == len(groups["macos"][name]) == 1:
        pair("console-group", name, [groups["windows"][name][0]["seconds"]],
             [groups["macos"][name][0]["seconds"]],
             [f"workflow-console.log:{groups[os][name][0]['lines']}" for os in reports],
             "Log marker interval, not CPU time; nested groups overlap.")

imports = {}
import_totals = {}
ambiguous_imports = {}
for os in reports:
    text = read(INPUT / os / "ci" / "logs" / "021-diagnostic-importtime-UNMEASURED.stderr.log")
    parsed = []
    for line in text.splitlines():
        match = re.match(r"import time:\s*(\d+)\s*\|\s*(\d+)\s*\|(.*)", line)
        if match:
            parsed.append({"module": match[3].strip(), "self_us": int(match[1]),
                           "cumulative_us": int(match[2]),
                           "indent": len(match[3]) - len(match[3].lstrip())})
    assert text.count("import time: self") == 1
    counts = Counter(p["module"] for p in parsed)
    ambiguous_imports[os] = {name: n for name, n in counts.items() if n > 1}
    import_totals[os] = sum(p["self_us"] for p in parsed) / 1e6
    imports[os] = {p["module"]: p for p in parsed if counts[p["module"]] == 1}
for module in imports["windows"].keys() & imports["macos"].keys():
    pair("parent-import-self", module, [imports["windows"][module]["self_us"] / 1e6],
         [imports["macos"][module]["self_us"] / 1e6],
         [f"{os}\\ci\\logs\\021-diagnostic-importtime-UNMEASURED.stderr.log#{module}" for os in reports],
         "Matched module, single parent python -X importtime -m build --no-isolation context; "
         "one diagnostic per OS; backend hook subprocess coverage absent. Self only.")
pair("parent-import-total", "observed-exclusive-import-self",
     [import_totals["windows"]], [import_totals["macos"]],
     ["021-diagnostic-importtime-UNMEASURED.stderr.log"],
     "Exclusive self sum includes platform-specific modules; never sum cumulative. "
     "Not a decomposition of normal uv build medians.")
for tier in sorted({r["tier"] for r in rows}):
    ranked = sorted((r for r in rows if r["tier"] == tier),
                    key=lambda r: (-r["absolute_gap_seconds"], r["phase"]))
    for rank, row in enumerate(ranked, 1):
        row["rank_within_tier"] = rank
rows.sort(key=lambda r: (r["tier"], r["rank_within_tier"], r["phase"]))
save("paired-timings.json", {
    "run_id": 40814588064, "source_sha": reports["windows"]["metadata"]["git_sha"],
    "strict_comparison": "REJECTED; historical observations only",
    "ranking": "descending absolute Windows-minus-Mac gap within nonadditive timing tiers",
    "raw_job_envelopes_excluded_from_comparison": raw,
    "windows_only_exclusions": excluded + [{"phase": n, "reason": "Windows-only step"} for n in extra_steps],
    "metadata": {os: r["metadata"] for os, r in reports.items()},
    "diagnostic_commands": {os: r["commands"][-1] for os, r in reports.items()},
    "rows": rows,
})
save("log-coverage.json", {"commands": coverage, "console_groups": groups,
                         "unique_parent_import_rows": imports,
                         "repeated_modules_excluded_from_pairing": ambiguous_imports})
fields = ["tier", "rank_within_tier", "phase", "windows_seconds", "macos_seconds",
          "windows_minus_macos_seconds", "absolute_gap_seconds", "windows_over_macos",
          "windows_n", "macos_n", "windows_range", "macos_range", "note"]
with (OUT / "gap-priority.csv").open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
save("source-hashes.json", used)
for tier in ["workflow-step", "console-group", "normal-full-build", "bootstrap-command",
             "parent-import-total", "parent-import-self", "job-envelope"]:
    print(tier)
    for row in [r for r in rows if r["tier"] == tier][:8]:
        print(row["phase"], round(row["windows_seconds"], 6), round(row["macos_seconds"], 6),
              "gap", round(row["windows_minus_macos_seconds"], 6))
