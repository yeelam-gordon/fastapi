"""Post-build verification and functional inventory, never clean-build timing."""
import ast
import json
from pathlib import Path
import statistics
import subprocess
import zipfile

import run


def wheel_exec(directory):
    with zipfile.ZipFile(next(directory.glob("*.whl"))) as archive:
        return {member.filename: bool((member.external_attr >> 16) & 0o111)
                for member in archive.infolist() if not member.is_dir()}


def main():
    evidence = json.loads((run.HERE / "evidence.json").read_text())
    assert len(evidence["summary"]) == 6
    expected_exec = wheel_exec(run.MAC)
    runtime_command = [run.NODE, "-p", "JSON.stringify({version:process.version,arch:process.arch})"]
    evidence["node_runtime"] = json.loads(subprocess.check_output(runtime_command, text=True))
    evidence["node_runtime_command"] = runtime_command
    assert evidence["node_runtime"] == {"version": "v24.21.0", "arch": "arm64"}
    roots = {v: Path(p) for v, p in evidence["roots"].items()}
    snapshots = []
    for row in evidence["trials"]:
        suffix = "-resume" if row["trial"] == 3 and row["algorithm"] != "selective-pdm" else ""
        label = f'{row["algorithm"]}-{row["trial"]}{suffix}'
        directory = roots[row["volume"]] / "runs" / label
        artifacts = directory / "outputs" / label / "artifacts"
        assert wheel_exec(artifacts) == expected_exec
        metadata_roots = [directory / "source" / ".pdm-build"]
        metadata_roots.extend(p / ".pdm-build" for p in
                              (directory / "outputs" / label / "extracted").iterdir())
        metadata = [p for root in metadata_roots if root.exists()
                    for p in root.rglob("*") if p.is_file()]
        snapshots.append({"volume": row["volume"], "label": label,
            "wheel_exec_bits_match_mac": True,
            "retained_metadata_files": len(metadata),
            "retained_metadata_bytes": sum(p.stat().st_size for p in metadata),
            "metadata_relative_paths": [str(p.relative_to(directory)) for p in metadata],
            "retained_temp_files": sum(p.is_file() for p in (directory / "temp").rglob("*")),
            "retained_cache_files": sum(p.is_file() for p in (directory / "cache").rglob("*")),
            "materialized_extracted_files": row["extracted_files"],
            "archive_writes": row["archive_writes"], "archive_bytes": row["archive_bytes"]})
    def selector(path):
        return next(n for n in ast.parse(path.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == "select")
    assert ast.dump(selector(run.ORIGINAL / "selective_inputs.py")) == ast.dump(selector(
        run.LAB / "round-2" / "overhead" / "selective.py"))
    for volume, root in roots.items():
        for name in ("experiment.py", "writer.cjs", "selective_inputs.py", "baseline.py", "selective_pdm.py"):
            target = run.HERE / ("execution-" + name)
            source = root / "code" / name
            if target.exists():
                assert target.read_bytes() == source.read_bytes()
            else:
                target.write_bytes(source.read_bytes())
    evidence["functional_inventory"] = snapshots
    evidence["wheel_exec_validation"] = "passed all completed trials"
    evidence["selector_ast_matches_original_overhead_selective"] = True
    evidence["count_boundaries"] = {
        "source_inventory": "3390 canonical files materialized per excluded checkout preparation; hashes checked in primary batch",
        "selected_payloads": "1268 PDM selected archive inputs plus generated PKG-INFO; not filesystem read syscall tracing",
        "extraction": "1269 regular files for full PDM versus 64 archive-derived files for selective variants",
        "metadata": "Post-build retained .pdm-build files only; transient create/delete and OS scanner opens not observed",
        "archive_writes": "2 completed archives; low-level write syscall count and bytes written by filesystem not observed",
        "cpu": "Python process_time; Node and security scanner CPU are not captured"}
    evidence["driver_copy_sha256"] = {p.name: run.sha(p) for p in run.HERE.glob("execution-*")}
    evidence["optional_scanner_cpu"] = {
        "samples": [json.loads(p.read_text(encoding="utf-8-sig"))
                    for p in run.HERE.glob("MsMpEng-*.json")],
        "scope": "Partial supplemental batch only; aggregate shared-host CPU, not per-trial scan attribution.",
        "etw": "No ETW recording authorized or started."}
    evidence["phase_medians"] = []
    for cell in evidence["summary"]:
        rows = [r for r in evidence["trials"] if r["volume"] == cell["volume"]
                and r["algorithm"] == cell["algorithm"]]
        evidence["phase_medians"].append({
            "volume": cell["volume"], "algorithm": cell["algorithm"],
            "imports_seconds": statistics.median(r["imports_seconds"] for r in rows),
            "sdist_seconds": statistics.median(r["sdist_seconds"] for r in rows),
            "selection_extraction_seconds": statistics.median(
                r.get("select_extract_seconds", r.get("extract_seconds")) for r in rows),
            "wheel_seconds": statistics.median(r["wheel_seconds"] for r in rows)})
    (run.HERE / "evidence.json").write_text(json.dumps(evidence, indent=2))
    lines = ["Controlled C/Q filesystem workload experiment",
             "",
             "Median full Python spawn-to-exit seconds (warm OS caches; fresh source/output/temp/cache).",
             "Volume | pipeline | n | seconds | Python CPU s | archive bytes | extracted | strict Mac",
             "------ | -------- | - | ------- | ------------ | ------------- | --------- | ----------"]
    for row in evidence["summary"]:
        lines.append(f'{row["volume"]} | {row["algorithm"]} | {row["n"]} | '
                     f'{row["median_wall_seconds"]:.4f} | {row["median_python_cpu_seconds"]:.4f} | '
                     f'{row["median_archive_bytes"]:.0f} | {row["extracted_files"]} | '
                     f'{row["strict_passes"]}/{row["n"]}')
    lines += ["", "Median child phases: imports / sdist / selection+extraction / wheel (seconds)."]
    for row in evidence["phase_medians"]:
        lines.append(f'{row["volume"]} {row["algorithm"]}: {row["imports_seconds"]:.4f} / '
                     f'{row["sdist_seconds"]:.4f} / {row["selection_extraction_seconds"]:.4f} / '
                     f'{row["wheel_seconds"]:.4f}')
    lines += ["", "Excluded preparation (not part of those build timings):"]
    for cell in evidence["summary"]:
        rows = [r for r in evidence["trials"] if r["volume"] == cell["volume"]
                and r["algorithm"] == cell["algorithm"]]
        lines.append(f'{cell["volume"]} {cell["algorithm"]} median fresh source preparation '
                     f'{statistics.median(r["source_preparation_seconds"] for r in rows):.3f}s.')
    for row in evidence["preparation"]:
        lines.append(f'{row["volume"]} one-time env/code/input/wheelhouse preparation {row["seconds"]:.3f}s.')
    lines += ["", "Strict comparison includes every raw payload, wheel RECORD validation/raw bytes,",
              "full sdist modes and wheel executable bits. Ordinary PDM fails exactly five sdist",
              "executable modes (0755 -> 0644); this is an overall strict failure, not waived.",
              "Node and selective-PDM pass; selective-PDM uses official PDM TAR serialization,",
              "the unchanged archive-derived selector and a small Git-mode clean_tarinfo adapter.",
              "No project metadata, selected-member list or payload cache is reused.",
              "", "Functional workload:",
              "3390 canonical files per excluded source checkout; each build freshly selects",
              "1268 PDM archive inputs and generates PKG-INFO. Each completed sdist has 1269",
              "files, wheel 65. Full extraction materializes 1269; selective materializes 64",
              "(1205 fewer, 94.96%). Selection still enumerates all archive members and reads",
              "pyproject for configuration; PDM still inventories the source. It does NOT remove",
              "the initial sdist payload reads. All variants write two complete archives.",
              "Retained metadata/temp/cache inventories are in evidence.json; these are snapshots,",
              "not total file creates or scan events. Python CPU excludes Node/scanner CPU.",
              "", "Placement/provenance:",
              "C NTFS / Q ReFS per supplied read-only volume observation. Dev Drive trust and",
              "performance-mode state were not verified (queries denied); no protection changes.",
              "C native env, PDM/backend libraries, copied drivers, source/mode manifest, wheelhouse,",
              "cache/temp and outputs all reside in owned C workspace; base Python and Node also C.",
              "Q uses equivalent private env and algorithms, with the same C base Python/Node.",
              "Offline tooling restored from tooling.lock using existing uv; pdm-backend 2.5.0.",
              "Code hashes, exact argv/cwd, provisioning and per-trial checkout cost are recorded.",
              "Primary batch was bounded after two pairs; partial source-only third checkout",
              "is retained and never reused. Three final pairs per primary cell are completed.",
              "",
              "Inference limits:",
              "Absolute speedups and the C/Q interaction are local workload evidence only.",
              "No scan trace: no causal Defender/MDE attribution. NTFS/ReFS, device differences,",
              "OS cache warmth and background work are confounders. No cold-cache claim.",
              "Generic optimizations may also accelerate Mac: NO parity claim against frozen Mac.",
              "Mac artifacts are used as correctness oracle only, not optimized-Mac performance.",
              "High confidence: artifact checks and 1269->64 file-materialization reduction.",
              "Medium confidence: local warm-cache timing; low confidence: scanner attribution,",
              "CI transferability and any Windows-specific mechanism.",
              "Primary PDM/Node cells alternate algorithm order within each volume; the simpler",
              "PDM cells were a later three-pair supplement, so temporal confounding remains.",
              "Optional MsMpEng aggregate samples cover only the remaining supplemental interval.",
              "Unavailable process CPU is unknown, never zero; no paths/configuration/ETW collected.",
              "",
              "Commands (from Q:\\fastapi):",
              '$p = "Generated Files\\arm-build\\tools\\official-tool-environment\\Scripts\\python.exe"',
              '$r = "Generated Files\\arm-build\\filesystem\\c-vs-q"',
              '& $p "$r\\run.py"  # initial batch; deliberately stopped after two completed pairs',
              '& $p "$r\\run.py" --resume --bounded',
              '& $p "$r\\supplement.py"',
              '& $p "$r\\finalize.py"',
              "Scripts refuse fresh-root collisions; do not rerun without selecting new owned roots.",
              "All original workers and existing measured environments remain unchanged.",
              "No subagents, CI, new tool downloads, AV exclusions or machine configuration changes.",
              "", "Decision: do not adopt a custom archive writer from this bounded experiment.",
              "Selective-PDM wins on Q but REGRESSES on C despite 1205 fewer extracted files.",
              "Its C sdist median is ~7.13s versus stock PDM ~1.94s, while Python CPU is lower",
              "overall; this is a concrete unexplained stall, not proof of scanner involvement.",
              "Node's extra benefit is ~0.45s on Q and ~6.08s on C here, not a universal small gain.",
              "The baseline has incorrect executable modes; the simpler PDM adapter corrects them,",
              "so baseline versus selective is not a pure extraction-only causal comparison.",
              "Next bounded hypothesis: compare mode-correct stock-PDM full versus selective",
              "extraction with the same writer and fresh input policy, and separately obtain an",
              "approved scan trace to investigate the C sdist stall. No extra matrix was run now.",
              "Apply the same pipeline to Mac before making any cross-OS parity claim."]
    lookup = {(r["volume"], r["algorithm"]): r for r in evidence["summary"]}
    lines += ["", "Computed local comparisons:"]
    for volume in roots:
        base = lookup[volume, "pdm"]["median_wall_seconds"]
        selective = lookup[volume, "selective-pdm"]["median_wall_seconds"]
        node = lookup[volume, "node"]["median_wall_seconds"]
        lines.append(f"{volume}: baseline/selective {base/selective:.3f}x; baseline/Node {base/node:.3f}x; "
                     f"Node advantage over selective {selective-node:.4f}s ({(1-node/selective)*100:.1f}%).")
    for algorithm in ("pdm", "selective-pdm", "node"):
        c = lookup["C", algorithm]["median_wall_seconds"]
        q = lookup["Q", algorithm]["median_wall_seconds"]
        lines.append(f"{algorithm}: C-Q {c-q:.4f}s; C/Q {c/q:.3f}x.")
    baseline_gap = lookup["C", "pdm"]["median_wall_seconds"] - lookup["Q", "pdm"]["median_wall_seconds"]
    for algorithm in ("selective-pdm", "node"):
        optimized_gap = lookup["C", algorithm]["median_wall_seconds"] - lookup["Q", algorithm]["median_wall_seconds"]
        lines.append(f"Descriptive C/Q interaction for {algorithm}: "
                     f"baseline C-Q gap minus optimized C-Q gap = {baseline_gap-optimized_gap:.4f}s; "
                     "not an identified scanner effect.")
    lines += ["", "Evidence: evidence.json, per-trial timings/selection/manifests and stdout/stderr;",
              "execution-* are exact instrumented code copies. work/ and binary outputs are ignored;",
              "C workspace is retained disposable execution data, not a published sensitive trace."]
    (run.HERE / "REPORT.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
