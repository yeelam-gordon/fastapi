"""Verify persisted results and publish the bounded causal interpretation."""
import io
import json
from pathlib import Path
import pstats
import sys
import tarfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run


def main():
    evidence = json.loads((HERE / "evidence.json").read_text())
    assert evidence["status"] == "complete" and len(evidence["trials"]) == 9
    work = Path(evidence["source"]).parent
    executed = work / "code" / "worker.py"
    assert run.sha(executed) == evidence["worker_sha256"]
    (HERE / "execution-worker.py").write_bytes(executed.read_bytes())
    profile_dir = work / "outputs" / "profile-sdist-only" / "artifacts"
    with tarfile.open(next(profile_dir.glob("*.tar.gz"))) as archive:
        actual = {m.name: {"sha256": run.hashlib.sha256(archive.extractfile(m).read()).hexdigest(),
                          "exec": bool(m.mode & 0o111), "mode": m.mode}
                  for m in archive if m.isfile()}
    expected = run.members(run.MAC)["sdist"]
    assert actual == expected
    evidence["profile"]["strict_sdist_validation"] = "passed all raw payloads and full modes"
    stats = pstats.Stats(str(HERE / "sdist.pstats"))
    evidence["profile"]["adapter_functions"] = [
        {"file": key[0], "line": key[1], "function": key[2], "calls": value[1],
         "tottime_seconds": value[2], "cumtime_seconds": value[3]}
        for key, value in stats.stats.items()
        if key[2] in ("canonical_clean_tarinfo", "clean_tarinfo", "gettarinfo")]
    stream = io.StringIO()
    stats.stream = stream
    stream.write("UNTIMED DIAGNOSTIC: TOP 40 CUMULATIVE\n")
    stats.sort_stats("cumulative").print_stats(40)
    stream.write("\nUNTIMED DIAGNOSTIC: TOP 40 TOTAL\n")
    stats.sort_stats("tottime").print_stats(40)
    (HERE / "PROFILE-top40.txt").write_text(stream.getvalue())
    pdm = work.parent / "env" / "Lib" / "site-packages" / "pdm"
    pyc = list(pdm.rglob("*.pyc"))
    evidence["backend_bytecode_condition"] = {
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "observation_boundary": "after complete timed matrix; no pre-trial bytecode census was taken",
        "pdm_pyc_count": len(pyc),
        "pdm_pyc_bytes": sum(p.stat().st_size for p in pyc),
        "policy": "PYTHONDONTWRITEBYTECODE=1 in all trials; direct workers additionally set sys.dont_write_bytecode=True",
        "caveat": "The flag prevents writes, not loading existing bytecode. This is not assumed to model prepared CI backend bytecode.",
        "compileall": "not run; no mid-trial environment mutation or additional matrix"}
    for row in evidence["trials"]:
        if row["variant"] == "uv":
            differences = row["validation"]["differences"]
            assert len(differences) == 5
            assert all(d["kind"] == "sdist" and
                       d["expected"]["sha256"] == d["actual"]["sha256"] and
                       d["expected"]["mode"] == 0o755 and d["actual"]["mode"] == 0o644
                       for d in differences)
    full = next(r for r in evidence["summary"] if r["variant"] == "full")
    selective = next(r for r in evidence["summary"] if r["variant"] == "selective")
    pairs = []
    for iteration in range(1, 4):
        f = next(r for r in evidence["trials"] if r["iteration"] == iteration and r["variant"] == "full")
        s = next(r for r in evidence["trials"] if r["iteration"] == iteration and r["variant"] == "selective")
        pairs.append({"iteration": iteration,
                      "full_minus_selective_seconds": f["full_process_seconds"] - s["full_process_seconds"],
                      "sdist_full_minus_selective_seconds": f["sdist_seconds"] - s["sdist_seconds"]})
    evidence["paired_deltas"] = pairs
    evidence["interpretation"] = {
        "extraction_reduction": "1269 to 64 regular files, 1205 fewer (94.96%)",
        "prior_stall": "Not reproduced: identical corrected writer is ~2.0s for both full and selective, versus historical selective ~7.13s.",
        "attribution": "Same writer and shared checkout isolate extraction strategy locally; no Defender/MDE causal attribution or Mac parity claim.",
        "next_small_proposal": "Screen this smaller mode-correct selective pipeline through the actual uv release frontend before considering any custom Node TAR writer."}
    (HERE / "evidence.json").write_text(json.dumps(evidence, indent=2))
    lines = ["Shared-checkout C: follow-up (no CI / protection changes / ETW)",
             "",
             f'Prepared exactly one canonical 3390-file checkout once: {evidence["source_preparation_seconds"]:.3f}s.',
             "This preparation and code/uv copy are excluded from build timings; the same source,",
             "C native env, pinned PDM 2.5.0, runtime temp/cache and mode manifest serve every trial.",
             "Each build uses a fresh output directory and fresh PDM metadata. Historical evidence",
             "was not modified. Child logs are captured in memory and published after timing.",
             "",
             "Pipeline | n | median spawn-to-exit seconds | range | strict Mac",
             "-------- | - | --------------------------- | ----- | ----------"]
    for row in evidence["summary"]:
        lo, hi = row["range_seconds"]
        lines.append(f'{row["variant"]} | {row["n"]} | {row["median_wall_seconds"]:.4f} | '
                     f'{lo:.4f}-{hi:.4f} | {row["strict_passes"]}/{row["n"]}')
    lines += ["",
              "uv is the REAL release frontend: uv build --no-build-isolation --python <Cenv>",
              "--offline --no-config --out-dir <fresh C output>, run from the single C checkout.",
              "It builds both sdist and wheel-from-sdist. All three builds complete and validate",
              "every payload and wheel RECORD (including raw bytes) and wheel exec bits, but all",
              "FAIL overall strict correctness: the same five sdist scripts lose 0755 -> 0644.",
              "Those five failures are not waived. Full/selective corrected workers pass 3/3 each.",
              "",
              "Identical corrected stock-PDM writer; only extraction strategy varies.",
              "Three pairs alternate full/selective, selective/full, full/selective; uv precedes",
              "each pair. No project metadata, selection list or payload cache is reused."]
    for row in (full, selective):
        phase = row["phase_medians"]
        lines.append(f'{row["variant"]}: imports {phase["imports_seconds"]:.4f}s; '
                     f'sdist {phase["sdist_seconds"]:.4f}s; extraction {phase["extraction_seconds"]:.4f}s; '
                     f'wheel {phase["wheel_seconds"]:.4f}s; Python CPU {phase["python_cpu_seconds"]:.4f}s.')
    difference = full["median_wall_seconds"] - selective["median_wall_seconds"]
    speedup = full["median_wall_seconds"] / selective["median_wall_seconds"]
    paired_text = ", ".join(f"{r['full_minus_selective_seconds']:.4f}s" for r in pairs)
    lines += [f"Corrected full -> selective: {difference:.4f}s less wall time ({speedup:.3f}x).",
              f"Paired full-minus-selective deltas: {paired_text}.",
              "Extraction drops 1269 -> 64 files (1205 fewer, 94.96%); all 1269 sdist members",
              "are still enumerated and the same source payloads still feed the same stock writer.",
              "",
              "Prior 7.129s C sdist stall is NOT reproduced: both corrected-writer variants now",
              "spend ~2.0s in sdist. Thus the old 8.443s result was not an intrinsic selective-",
              "extraction cost; reused source, temporal/cache/host conditions remain confounders.",
              "This follow-up does not establish which changed condition removed that stall.",
              "",
              f'One separately profiled sdist only: {evidence["profile"]["profiled_total_seconds"]:.4f}s',
              "(instrumented diagnostic, NEVER treated as a clean benchmark sample).",
              "Top 40 cumulative and total time: PROFILE-top40.txt and evidence.json.",
              "Largest self-time functions:"]
    for row in evidence["profile"]["top40_tottime"][:8]:
        lines.append(f'  {row["function"]}: {row["calls"]} calls; self {row["tottime_seconds"]:.4f}s; '
                     f'cumulative {row["cumtime_seconds"]:.4f}s.')
    lines.append("Adapter/stat helper costs:")
    for row in evidence["profile"]["adapter_functions"]:
        lines.append(f'  {row["function"]}: {row["calls"]} calls; self {row["tottime_seconds"]:.4f}s; '
                     f'cumulative {row["cumtime_seconds"]:.4f}s.')
    lines += ["The current sdist profile localizes cost mainly to many file opens, compression",
              "and filesystem metadata operations, not expensive mode-adapter Python computation.",
              "cProfile includes wait inside calls but cannot identify security-scanner ownership.",
              "Because the earlier 7.13s stall did not recur, this does not retrospectively localize",
              "the missing ~5s. No system trace was authorized or started.",
              "",
              f'Backend bytecode census AFTER matrix: {len(pyc)} PDM .pyc files, '
              f'{sum(p.stat().st_size for p in pyc)} bytes.',
              "No before-trial census exists. PYTHONDONTWRITEBYTECODE=1 was constant; direct",
              "workers also set sys.dont_write_bytecode=True. Existing pyc can still be read;",
              "do not equate these import timings to CI prepared with backend bytecode.",
              "No compileall screen was added and no environment was mutated mid-trial.",
              "",
              "Decision / next SMALL proposal:",
              "Prefer screening the smaller, mode-correct selective PDM pipeline through uv's",
              "actual release frontend before maintaining a custom Node TAR writer. Keep PDM",
              "metadata fresh. Separately provision/report backend bytecode if matching warmed",
              "CI imports becomes the next target; do not merge that change into extraction proof.",
              "No Windows-specific scanner causation or optimized-Mac parity is claimed.",
              "",
              "Commands from Q:\\fastapi:",
              '$p = "Generated Files\\arm-build\\tools\\official-tool-environment\\Scripts\\python.exe"',
              '$r = "Generated Files\\arm-build\\filesystem\\c-vs-q\\followup"',
              '& $p "$r\\run_followup.py"  # refuses existing workspace; preserve it',
              '& $p "$r\\summarize.py"',
              "Exact child argv/cwd, environment overrides, timings, manifests and raw logs:",
              "evidence.json, *-manifest.json, *.stdout.log, *.stderr.log.",
              "execution-worker.py and receipt hash identify the exact executed worker;",
              "worker.py differs only by removing an unused import after measurement.",
              "High confidence: strict artifacts and local extraction comparison; medium:",
              "three-pair warm repeated-job timing; unknown: historical stall/scanner mechanism."]
    (HERE / "REPORT.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    main()
