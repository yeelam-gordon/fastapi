"""Ordinary fresh PDM sdist, full extraction, then fresh wheel."""
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
start = time.perf_counter()
cpu = time.process_time()
audit = {"python_read_opens": 0, "python_write_opens": 0, "mkdir_events": 0,
         "source_read_opens": 0, "metadata_write_opens": 0}
source = Path(os.environ["LAB_SOURCE"])
if os.environ.get("LAB_AUDIT") == "1":
    def observe(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = str(args[0])
            flags = args[2] if isinstance(args[2], int) else 0
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
            audit["python_write_opens" if write else "python_read_opens"] += 1
            if not write and path.startswith(str(source)):
                audit["source_read_opens"] += 1
            if write and (".pdm-build" in path or "PKG-INFO" in path):
                audit["metadata_write_opens"] += 1
        elif event == "os.mkdir":
            audit["mkdir_events"] += 1
    sys.addaudithook(observe)

import tarfile
from pdm.backend.sdist import SdistBuilder
from pdm.backend.wheel import WheelBuilder

imported = time.perf_counter()
output = Path(os.environ["LAB_WORK"]) / sys.argv[1]
artifacts, extracted = output / "artifacts", output / "extracted"
artifacts.mkdir(parents=True)
extracted.mkdir()
with SdistBuilder(source) as builder:
    sdist = builder.build(str(artifacts))
after_sdist = time.perf_counter()
with tarfile.open(sdist) as archive:
    entries = archive.getmembers()
    files = [member for member in entries if member.isfile()]
    archive.extractall(extracted, filter="data")
after_extract = time.perf_counter()
roots = list(extracted.iterdir())
assert len(roots) == 1
with WheelBuilder(roots[0]) as builder:
    builder.build(str(artifacts))
end = time.perf_counter()
row = {"child_seconds": end - start, "imports_seconds": imported - start,
       "sdist_seconds": after_sdist - imported,
       "extract_seconds": after_extract - after_sdist,
       "wheel_seconds": end - after_extract,
       "python_cpu_seconds": time.process_time() - cpu,
       "extracted_files": len(files), "archive_files": len(files),
       "audit": audit if os.environ.get("LAB_AUDIT") else None}
(Path(__file__).parent / f"{sys.argv[1]}-timings.json").write_text(json.dumps(row, indent=2))
