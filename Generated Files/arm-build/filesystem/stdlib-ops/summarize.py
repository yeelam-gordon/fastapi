import json
from collections import Counter
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "evidence.json").read_text())
assert data["status"] == "complete", data.get("error", data["status"])
rows = {r["variant"]: r for r in data["summary"]}
samples = {(r["label"].split("-")[0], r["variant"]): r
           for r in data["trials"]}
lines = [
    "Bounded C-drive stdlib I/O experiment (not a release adoption)",
    "",
    "Four cells use the SAME PDM 2.5 subclass, stdlib tarfile/PAX/gzip level 9.",
    "seq reads each input into bytes; thread overlaps fresh reads using three",
    "workers and a three-future window (approximately four live payload buffers).",
    "Both cells regenerate PDM selection/config/metadata on every build.",
    "The source checkout Git-mode manifest restores all executable sdist inputs",
    "in EVERY cell, including baseline. No custom format writer or foreign patch.",
    "",
    "variant | wall samples (s) | median wall | imports | sdist | extract | wheel",
    "------- | ---------------- | ----------- | ------- | ----- | ------- | -----",
]
for variant, row in rows.items():
    m = row["medians"]
    lines.append(f"{variant} | {', '.join(f'{v:.4f}' for v in row['samples'])} | "
                 + " | ".join(f"{m[k]:.4f}" for k in ("wall_seconds", "imports_seconds",
                     "sdist_seconds", "extraction_seconds", "wheel_seconds")))
lines += ["", "Paired savings (baseline minus candidate; positive is faster):"]
comparisons = [("seq-attrs", "seq-noattrs"), ("thread-attrs", "thread-noattrs"),
               ("seq-attrs", "thread-attrs"), ("seq-noattrs", "thread-noattrs"),
               ("seq-attrs", "thread-noattrs")]
for baseline, candidate in comparisons:
    deltas = [samples[(str(i), baseline)]["wall_seconds"] -
              samples[(str(i), candidate)]["wall_seconds"] for i in range(1, 4)]
    lines.append(f"{baseline} -> {candidate}: "
                 f"{', '.join(f'{d:.4f}' for d in deltas)}; median {statistics.median(deltas):.4f}s")
lines += ["", "Separate process audit events (instrumented, excluded from clean timings):"]
for row in data["diagnostics"]:
    if row.get("warmup"):
        continue
    lines.append(row["variant"] + ": " + json.dumps(row["audit"], sort_keys=True))
lines += [
    "Absent event keys are ZERO. Total opens are 1617 in every diagnostic;",
    "total chmod 65 -> 1 and utime 64 -> 0 when skipping temporary attributes.",
    "These are Python audit events, not kernel syscall counts or scanner counts.",
]
baseline = rows["seq-attrs"]["medians"]["wall_seconds"]
combined = rows["thread-noattrs"]["medians"]["wall_seconds"]
reference = json.loads((HERE / "reference-manifest.json").read_text())
lines += [
    "",
    "Proposal decision (bounded screen only):",
    "PREFETCH: retain as the meaningful small follow-up proposal, not adoption.",
    "Paired savings are positive in all three pairs with either attr setting;",
    "the sdist phase falls ~1.970 -> 1.123s with attrs held constant. The same",
    "1268 disk-backed sdist payloads are freshly read; PKG-INFO is freshly generated.",
    "NOATTRS: retain only the guarded disposable-0644-input optimization. It removes",
    "64 chmod + 64 utime audit events, with smaller but positive paired savings.",
    f"COMBINED: median wall {baseline:.4f} -> {combined:.4f}s "
    f"({100*(baseline-combined)/baseline:.1f}% less, {baseline/combined:.3f}x).",
    "Do not replace release tooling on these data alone. The 73-line ops.py core",
    "includes a private PDM build_artifact override: medium maintenance/API risk,",
    "pinned to PDM 2.5.0. Prefer a small supported/upstream hook over a framework",
    "or a format rewrite. Common portable options should also be screened on Mac.",
    "Confidence: high on this archive/permission validation and audited event",
    "difference; medium on the local warm speed benefit; unknown on cross-host",
    "or Mac benefit and the underlying file-wait/scanner mechanism.",
    "Normative sdist mode census: " + json.dumps(dict(Counter(
        oct(v["mode"]) for v in reference["sdist"].values())), sort_keys=True),
    "Normative wheel FULL mode census: " + json.dumps(dict(Counter(
        oct(v["full_mode"]) for v in reference["wheel"].values())), sort_keys=True),
]
lines += [
    "",
    "Correctness: all 12 timed builds plus diagnostics validate against the retained",
    "Mac normative archives: exactly 1269 sdist members, 65 wheel members; complete",
    "member names/payload SHA256, sdist full permission modes and uid/gid/uname/gname/",
    "size, wheel full external_attr>>16 modes, raw wheel RECORD bytes and each RECORD",
    "hash/size. No executable-bit-only waiver. Timestamps/container byte equality",
    "are not required (wall-clock generated metadata); no optimized-Mac speed claim.",
    "Wheel inputs come ONLY from each completed sdist: fresh archive-derived selector",
    "and 64 materializations, no source fallback or payload/selection cache.",
    "Noattrs refuses any selected member not exactly regular 0644 BEFORE extracting.",
    "Both extract paths call public TarFile.extract(..., filter='data').",
    "",
    "Focused tests: tests.log; fresh reads/order, read-failure and early-close thread",
    "joining, extracted payload/mtime behavior, exec/private/read-only rejection,",
    "path traversal filter in both modes, malformed archive and selector config guards.",
    "",
    f"Bootstrap/tool restore/copy: {data['bootstrap_seconds']:.3f}s (excluded).",
    f"One source preparation + SHA verification: {data['source_preparation_seconds']:.3f}s (excluded).",
    "All benchmark source/libs/runtime/temp/output on C. Q only controller and",
    "post-timer logs/manifests. Fresh output and child process per build; imports,",
    "metadata, selection, all source reads, compression, extraction and wheel inside",
    "spawn-to-exit wall timer. One audited warmup precedes alternating/reversed",
    "four-cell orders; OS cache is warm. Three trials cannot completely balance",
    "four ordinal positions; all pairs reverse at least once. No profiler in",
    "measured children. The 12 clean children take ~34 seconds in total.",
    "",
    "Provenance: " + json.dumps(data["runtime"], sort_keys=True),
    "base interpreter: " + data["base_exe"],
    "base executable SHA256: " + data["base_exe_sha256"],
    "python313.dll SHA256: " + data["python_dll_sha256"],
    "venv launcher SHA256: " + data["venv_exe_sha256"],
    "Managed CPython 3.13.15 ARM64 (uv python find --managed-python). The published",
    "standalone catalogue maps this family to Windows PGO; this is not exact",
    "compiler-flag proof for the local bytes. Prior 5.014/6.275/3.300s samples used",
    "the older installed stock distribution; do NOT subtract these sample sets",
    "or attribute cross-distribution differences to this change or pure PGO.",
    "Code hashes: " + json.dumps(data["code_hashes"], sort_keys=True),
    "Tool lock SHA256: " + data["lock_sha256"],
    "Source manifest SHA256: " + data["manifest_sha256"],
    "",
    "Limits: three warm local trials per cell, shared-host/cache/order noise; no",
    "scan count measurement or MDE/ETW trace, no scanner causal claim. Prefetch",
    "still performs the same payload opens and DOES NOT reduce ScanCount.",
    "Attribute skipping intentionally discards temporary chmod/utime only, not",
    "final artifact permissions. CPU is Python process_time (all its threads).",
    "No CI, Defender/UAC/trust/global settings changes, or base runtime installs.",
    "This is distinct from crutkas's source-only pip Windows Thread bytecode fix;",
    "build 1.6.1 pip --no-compile bypasses that code; no claim about that fix.",
    "Both proposals are portable in principle, including Mac where applicable,",
    "but were NOT benchmarked against an equivalently optimized live Mac pipeline.",
]
(HERE / "REPORT.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines[:30]))
