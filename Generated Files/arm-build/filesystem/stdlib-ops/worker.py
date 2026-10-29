import json
import os
from pathlib import Path
import sys
import time

start = time.perf_counter()
cpu = time.process_time()
variant, source, manifest, output = sys.argv[1:5]
output = Path(output)
audit = {}
stage = "imports"
if os.environ.get("LAB_AUDIT"):
    def observe(event, args):
        if event in ("open", "os.chmod", "os.utime"):
            key = stage + ":" + event
            audit[key] = audit.get(key, 0) + 1
    sys.addaudithook(observe)

import tarfile
from ops import BufferedSdistBuilder, extract_selected
from pdm.backend.wheel import WheelBuilder
from selector import select

BufferedSdistBuilder.threaded = variant.startswith("thread")
BufferedSdistBuilder.modes = json.loads(Path(manifest).read_text())
imported = time.perf_counter()
stage = "sdist"
artifacts = output / "artifacts"
artifacts.mkdir()
with BufferedSdistBuilder(Path(source)) as builder:
    sdist = builder.build(str(artifacts))
after_sdist = time.perf_counter()
stage = "extract"
extracted = output / "extracted"
extracted.mkdir()
with tarfile.open(sdist) as archive:
    selection = select(archive, extracted)
    extract_selected(archive, extracted, selection["member_names"],
                     not variant.endswith("noattrs"))
after_extract = time.perf_counter()
stage = "wheel"
roots = list(extracted.iterdir())
assert len(roots) == 1
with WheelBuilder(roots[0]) as builder:
    builder.build(str(artifacts))
end = time.perf_counter()
row = dict(variant=variant, imports_seconds=imported-start,
           sdist_seconds=after_sdist-imported,
           extraction_seconds=after_extract-after_sdist,
           wheel_seconds=end-after_extract, child_seconds=end-start,
           python_cpu_seconds=time.process_time()-cpu,
           selection=selection, audit=audit)
print("\nTIMING_JSON=" + json.dumps(row), file=sys.stderr)
