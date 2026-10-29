# Windows ARM build optimization

The top-level [PERSONA.md](../PERSONA.md) and [GOALS.md](../GOALS.md) own the expert operating method and requested outcomes. Start with [FINDINGS.md](FINDINGS.md) for results and limitations. [WORKBOARD.md](WORKBOARD.md) owns execution state; [SOURCES.md](SOURCES.md) records verified primary research; [PROFILING.md](PROFILING.md) applies that method to diagnostics.

The experiment preserves FastAPI's PDM backend and complete source-distribution-to-wheel build. It compares normal isolation with a separately provisioned pinned backend. It does not change FastAPI runtime behavior or publishing.

The current host's successful setup and exact benchmark commands are in [LOCAL-SETUP.md](LOCAL-SETUP.md). That uses the official GitHub backend source because PyPI binary TLS is blocked. On an unrestricted network, `provision.ps1` installs the complete hash-locked tool environment instead.

Every benchmark output directory must be new. Source is a `git archive HEAD` snapshot, so commit intended source changes first; uncommitted changes are recorded but excluded. Each run retains commands, logs, medians, ranges and archive member manifests. Provisioning is not included in build-only medians.

If PyPI wheel downloads are unavailable locally, download the `windows-arm-wheelhouse` artifact from the experiment workflow into `wheelhouse`, then pass `-Wheelhouse '.\Generated Files\arm-build\wheelhouse'` to `provision.ps1` and `--wheelhouse '.\Generated Files\arm-build\wheelhouse'` to the benchmark.

CI is opt-in through `.github\workflows\arm-build-experiment.yml`. The initial OAuth-scope blocker is now resolved; execution results are pending. [CI.md](CI.md) records authorization and dispatch steps. The lane selects explicit Windows 11 ARM64 and macOS ARM64 jobs, checks installed-wheel behavior and retains evidence on failure. Raw archives, tool binaries, environments and traces are excluded from Git; textual measurements and research are retained here.
