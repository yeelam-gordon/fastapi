# Windows ARM build optimization

The top-level [PERSONA.md](../PERSONA.md), [GOALS.md](../GOALS.md) and [CIRCUMSTANCES.md](../CIRCUMSTANCES.md) own the expert method, requested outcomes and working constraints. Start with [FINDINGS.md](FINDINGS.md) for results and limitations. [WORKBOARD.md](WORKBOARD.md) owns execution state; [SOURCES.md](SOURCES.md) records verified primary research; [PROFILING.md](PROFILING.md) applies that method to diagnostics.

The goal remains active. [INVESTIGATION-AND-PROPOSALS.md](../INVESTIGATION-AND-PROPOSALS.md) is the live table of measured proposals and next experiments; first-round completion does not mean parity was reached.

The experiment preserves FastAPI's PDM backend and complete source-distribution-to-wheel build. It compares normal isolation with a separately provisioned pinned backend. It does not change FastAPI runtime behavior or publishing.

The current host's setup and exact commands are in [LOCAL-SETUP.md](LOCAL-SETUP.md). Initial measurements used official GitHub backend source because PyPI binary TLS was blocked; the successful Windows job subsequently supplied an offline wheelhouse for the complete tool/minimal-runtime environment.

Every benchmark output directory must be new. Source is a `git archive HEAD` snapshot, so commit intended source changes first; uncommitted changes are recorded but excluded. Each run retains commands, logs, medians, ranges and archive member manifests. Provisioning is not included in build-only medians.

The corrected harness disables archive newline conversion and records a canonical source manifest. Captured `results` are stored without Git text conversion so raw report/harness hashes survive checkout. Earlier observations and rejected comparisons remain intact as history.

If PyPI wheel downloads are unavailable locally, download the `windows-arm-wheelhouse` artifact from the experiment workflow into `wheelhouse`, then pass `-Wheelhouse '.\Generated Files\arm-build\wheelhouse'` to `provision.ps1` and `--wheelhouse '.\Generated Files\arm-build\wheelhouse'` to the benchmark.

CI is opt-in through `.github\workflows\arm-build-experiment.yml`. Two runs were used: the first exposed a Mac architecture-guard bug, and the second passed both ARM jobs and installed-wheel smokes. Strict postprocessing still rejected cross-platform artifact differences; the source-newline correction was then validated locally, without a third CI run. [CI.md](CI.md) records the disposition. Raw archives, tool binaries, environments and traces are excluded from Git; textual measurements and research are retained here.
