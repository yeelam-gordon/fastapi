"""Three fresh paired trials: official PDM TAR writer + selective extraction."""
import json
import os
from pathlib import Path
import shutil
import statistics
import tarfile
import time

import run


def main():
    run.receipt = json.loads((run.HERE / "evidence.json").read_text())
    assert run.receipt.get("status") == "complete", "Run only after primary batch finishes"
    expected = run.members(run.MAC)
    roots = {v: Path(p) for v, p in run.receipt["roots"].items()}
    original = (run.HERE / "baseline.py").read_text()
    # Keep official PDM archive serialization; fix only Windows' lost Git exec bits.
    fixed = original.replace(
        "imported = time.perf_counter()",
        '''from selective_inputs import select
import pdm.backend.sdist as sdist_module
modes = json.loads((Path(os.environ["LAB_INPUT"]) / "source-manifest.json").read_text())
official_clean_tarinfo = sdist_module.clean_tarinfo
def canonical_clean_tarinfo(info):
    info = official_clean_tarinfo(info)
    relative = info.name.split("/", 1)[1]
    if relative in modes:
        info.mode = 0o755 if modes[relative]["mode"] & 0o111 else 0o644
    return info
sdist_module.clean_tarinfo = canonical_clean_tarinfo
imported = time.perf_counter()''')
    fixed = fixed.replace('archive.extractall(extracted, filter="data")',
                          'selection = select(archive, extracted)')
    fixed = fixed.replace('"extracted_files": len(files)', '"extracted_files": selection["selected_files"]')
    for root in roots.values():
        (root / "code" / "selective_pdm.py").write_text(fixed)
    (run.HERE / "selective_pdm.py").write_text(fixed)
    run.receipt["selective_pdm_code_sha256"] = run.sha(run.HERE / "selective_pdm.py")
    for number in range(1, 4):
        for volume in (["C", "Q"] if number % 2 else ["Q", "C"]):
            root = roots[volume]
            label = f"selective-pdm-{number}"
            directory = root / "runs" / label
            directory.mkdir()
            source = directory / "source"
            source.mkdir()
            begin = time.perf_counter()
            with tarfile.open(root / "inputs" / "source.tar") as archive:
                archive.extractall(source, filter="data")
            source_seconds = time.perf_counter() - begin
            for name in ("temp", "cache", "outputs"):
                (directory / name).mkdir()
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("UV_", "PIP_")) and k not in ("PYTHONPATH", "PYTHONHOME")}
            env.update(TEMP=str(directory / "temp"), TMP=str(directory / "temp"),
                       LOCALAPPDATA=str(directory / "cache"), XDG_CACHE_HOME=str(directory / "cache"),
                       PDM_CACHE_DIR=str(directory / "cache"), PYTHONNOUSERSITE="1",
                       PYTHONDONTWRITEBYTECODE="1", LAB_SOURCE=str(source),
                       LAB_INPUT=str(root / "inputs"), LAB_WORK=str(directory / "outputs"))
            env.pop("PDM_BUILD_NO_CLEAN", None)
            result, command = run.invoke(
                [root / "env" / "Scripts" / "python.exe", root / "code" / "selective_pdm.py", label],
                env, source)
            (run.HERE / f"{volume}-{label}.stdout.log").write_bytes(result.stdout)
            (run.HERE / f"{volume}-{label}.stderr.log").write_bytes(result.stderr)
            timing = root / "code" / f"{label}-timings.json"
            row = json.loads(timing.read_text())
            shutil.copyfile(timing, run.HERE / f"{volume}-{label}-timings.json")
            artifacts = directory / "outputs" / label / "artifacts"
            actual = run.members(artifacts)
            validation = run.validate(expected, actual)
            assert validation["strict_pass"], validation
            (run.HERE / f"{volume}-{label}-manifest.json").write_text(json.dumps(actual, indent=2))
            row.update(volume=volume, algorithm="selective-pdm", trial=number,
                       full_process_seconds=command["seconds"], validation=validation,
                       source_preparation_seconds=source_seconds, archive_writes=2,
                       archive_bytes=sum(p.stat().st_size for p in artifacts.iterdir()))
            run.receipt["trials"].append(row)
            run.save()
    for volume in roots:
        rows = [r for r in run.receipt["trials"] if r["volume"] == volume and r["algorithm"] == "selective-pdm"]
        run.receipt["summary"].append({"volume": volume, "algorithm": "selective-pdm", "n": len(rows),
            "median_wall_seconds": statistics.median(r["full_process_seconds"] for r in rows),
            "min_wall_seconds": min(r["full_process_seconds"] for r in rows),
            "max_wall_seconds": max(r["full_process_seconds"] for r in rows),
            "median_python_cpu_seconds": statistics.median(r["python_cpu_seconds"] for r in rows),
            "median_archive_bytes": statistics.median(r["archive_bytes"] for r in rows),
            "extracted_files": rows[0]["extracted_files"],
            "strict_passes": sum(r["validation"]["strict_pass"] for r in rows)})
    run.save()
    print(json.dumps(run.receipt["summary"], indent=2))


if __name__ == "__main__":
    main()
