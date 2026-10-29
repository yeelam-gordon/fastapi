# Windows ARM build optimization

Start with [FINDINGS.md](FINDINGS.md) for results and limitations. [WORKBOARD.md](WORKBOARD.md) owns goals and execution state; [SOURCES.md](SOURCES.md) records verified primary research; [PROFILING.md](PROFILING.md) explains the performance-engineering approach and subsequent profiling decisions.

The experiment preserves FastAPI's PDM backend and complete source-distribution-to-wheel build. It compares normal isolation with a separately provisioned pinned backend. It does not change FastAPI runtime behavior or publishing.

```powershell
& '.\Generated Files\arm-build\provision.ps1'
& '.\Generated Files\arm-build\.venv\Scripts\python.exe' '.\Generated Files\arm-build\test_benchmark.py'
& '.\Generated Files\arm-build\.venv\Scripts\python.exe' '.\Generated Files\arm-build\benchmark.py' --uv '.\Generated Files\arm-build\tools\uv.exe' --repeats 7 --output '.\Generated Files\arm-build\results\local-01' --importtime
```

Every benchmark output directory must be new. Source is a `git archive HEAD` snapshot, so commit intended source changes first; uncommitted changes are recorded but excluded. Each run retains commands, logs, medians, ranges and archive member manifests. Provisioning is not included in build-only medians.

If PyPI wheel downloads are unavailable locally, download the `windows-arm-wheelhouse` artifact from the experiment workflow into `wheelhouse`, then pass `-Wheelhouse '.\Generated Files\arm-build\wheelhouse'` to `provision.ps1` and `--wheelhouse '.\Generated Files\arm-build\wheelhouse'` to the benchmark.

CI is opt-in through `.github\workflows\arm-build-experiment.yml` on the owned fork. It runs explicit Windows 11 ARM64 and macOS ARM64 jobs, checks installed-wheel behavior and retains evidence even on failure. Raw archives, tool binaries, environments and traces are excluded from Git; textual measurements and research are retained here.
