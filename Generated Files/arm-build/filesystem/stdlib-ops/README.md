# Bounded stdlib file-operation screen

Results and decision: [REPORT.txt](REPORT.txt). Exact per-stage samples, commands,
runtime/code hashes and operation-count diagnostics: [evidence.json](evidence.json).
Focused tests: [tests.log](tests.log). `*-manifest.json` retain payload and full
permission evidence, checked against `reference-manifest.json`.

This is **not** release integration or a custom archive format. `ops.py` is a
73-line private PDM 2.5 experiment; `selector.py` is the existing archive-derived
selector, changed only to return members for the public filtered extractor.
Source modes come from the canonical checkout inventory, not Windows stat bits.
Neither baseline nor candidate waives executable/permission mismatches.

The measured comparison shares one prepared C checkout and one fresh offline
environment. All four cells use identical stdlib tarfile/PAX/gzip-9 output code.
Three-worker bounded prefetch changes read overlap, not file count. Optional
`set_attrs=False` is allowed only for disposable, regular **0644** wheel inputs.
Final wheel payloads and **full** modes must match the retained Mac archive.

## Reproduction

The completed workspace is retained at
`C:\fastapi-arm-build-lab\stdlib-ops-2a73e36a`; do not overwrite or reuse it for
another benchmark. `run.py` refuses an existing child. For a new bounded run,
first choose a different explicitly owned child and update `ROOT`.

```powershell
$python = 'C:\Users\yeelam\AppData\Roaming\uv\python\cpython-3.13.15-windows-aarch64-none\python.exe'
$here = 'Generated Files\arm-build\filesystem\stdlib-ops'
& $python "$here\run.py"       # refuses the already-completed workspace
& $python "$here\summarize.py" # report only; no new benchmark
```

Dependencies restore from the copied C wheelhouse with pinned hashes; nothing
installs into the base runtime. Source checkout, libraries, temporary files,
archive payloads and output live on C during timings. Q holds the controller
and post-timer evidence only. No CI, protection changes, ETW or subagents.

The Mac archive is a correctness reference, **not** an optimized speed baseline.
The managed interpreter differs from the older stock-distribution samples.
There is no scanner causation, ScanCount reduction, Mac parity or adoption claim.
