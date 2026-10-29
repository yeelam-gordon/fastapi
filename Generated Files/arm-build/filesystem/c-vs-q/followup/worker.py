"""Identical canonical-mode PDM writer; only extraction strategy varies."""
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
started, cpu = time.perf_counter(), time.process_time()
variant, source_name, manifest_name, output_name = sys.argv[1:]
source, manifest, output = map(Path, (source_name, manifest_name, output_name))
import tarfile
from pdm.backend.sdist import SdistBuilder
from pdm.backend.wheel import WheelBuilder
import pdm.backend.sdist as sdist_module
from selective_inputs import select

modes = json.loads(manifest.read_text())
official_clean_tarinfo = sdist_module.clean_tarinfo


def canonical_clean_tarinfo(info):
    info = official_clean_tarinfo(info)
    relative = info.name.split("/", 1)[1]
    if relative in modes:
        info.mode = 0o755 if modes[relative]["mode"] & 0o111 else 0o644
    return info


sdist_module.clean_tarinfo = canonical_clean_tarinfo
imported = time.perf_counter()
artifacts = output / "artifacts"
artifacts.mkdir()
if variant == "profile":
    import cProfile
    import pstats
    profiler = cProfile.Profile()
    profiler.enable()
    with SdistBuilder(source) as builder:
        sdist = builder.build(str(artifacts))
    profiler.disable()
    profiler.dump_stats(str(output / "sdist.pstats"))
    stats = pstats.Stats(profiler)
    rows = [{"file": key[0], "line": key[1], "function": key[2],
             "primitive_calls": value[0], "calls": value[1],
             "tottime_seconds": value[2], "cumtime_seconds": value[3]}
            for key, value in stats.stats.items()]
    result = {"scope": "UNTIMED cProfile of canonical-mode stock-PDM sdist only",
              "profiled_total_seconds": stats.total_tt,
              "top40_cumulative": sorted(rows, key=lambda r: r["cumtime_seconds"], reverse=True)[:40],
              "top40_tottime": sorted(rows, key=lambda r: r["tottime_seconds"], reverse=True)[:40]}
    print("\nPROFILE_JSON=" + json.dumps(result), file=sys.stderr)
    print("\nTOP 40 CUMULATIVE")
    stats.sort_stats("cumulative").print_stats(40)
    print("\nTOP 40 TOTAL")
    stats.sort_stats("tottime").print_stats(40)
else:
    with SdistBuilder(source) as builder:
        sdist = builder.build(str(artifacts))
    after_sdist = time.perf_counter()
    extracted = output / "extracted"
    extracted.mkdir()
    with tarfile.open(sdist) as archive:
        count = sum(member.isfile() for member in archive.getmembers())
        if variant == "selective":
            selected = select(archive, extracted)["selected_files"]
        else:
            assert variant == "full"
            archive.extractall(extracted, filter="data")
            selected = count
    after_extract = time.perf_counter()
    roots = list(extracted.iterdir())
    assert len(roots) == 1
    with WheelBuilder(roots[0]) as builder:
        builder.build(str(artifacts))
    ended = time.perf_counter()
    row = {"variant": variant, "child_seconds": ended - started,
           "imports_seconds": imported - started,
           "sdist_seconds": after_sdist - imported,
           "extraction_seconds": after_extract - after_sdist,
           "wheel_seconds": ended - after_extract,
           "python_cpu_seconds": time.process_time() - cpu,
           "archive_files": count, "extracted_files": selected}
    print("\nTIMING_JSON=" + json.dumps(row), file=sys.stderr)
