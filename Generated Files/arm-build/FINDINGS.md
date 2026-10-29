# FastAPI ARM build investigation

## What we can already conclude

FastAPI builds a pure-Python distribution, not a native executable. Adding compiler workers cannot accelerate compilation that does not exist. The first experiment measures package-backend and environment overhead while retaining PDM, the source distribution and the wheel built from that source distribution. Windows/macOS parity remains unproven until matched CI results are available.

The local machine is a 16-core Cobalt 100 Windows ARM64 VM, not the eventual approximately 20-core physical Windows machine. Native CPython 3.13.15 already works. A verified official ARM64 uv 0.13.6 distribution is installed locally. Windows Performance Recorder and Analyzer are present.

## Scope and evidence

The source revision is `79cab5bed28b24d92c185d236feb33f5783dfeb3`. The [workboard](WORKBOARD.md) owns goals, the expert operating method, task dependencies and current execution state. Raw local host evidence is in [host.json](results/environment/host.json).

| Question | Observed answer | Repository evidence |
|---|---|---|
| What is the package build? | `uv build` using `pdm.backend`; preserve both sdist and wheel | `pyproject.toml:1-3`; `.github/workflows/publish.yml:29-36` |
| What else enters the sdist? | Tests, documentation examples and scripts; removing them would change the deliverable | `pyproject.toml:213-221` |
| Is project-default Python native ARM64? | The project requests 3.11; the installed native interpreter is 3.13.15, selected explicitly | `.python-version:1`; host evidence |
| Are dependency setup and tests the same as a build? | No; existing test CI installs the broad test group and `all` extra, then executes coverage tests | `.github/workflows/test.yml:126,145-151` |
| Does existing CI explicitly select Windows ARM? | The audited workflow uses generic Windows/macOS labels, not an explicit Windows ARM label | `.github/workflows/test.yml:65-100` |
| Do more cores guarantee victory? | No; only parallel work benefits, and hardware, filesystem and runner resources differ | Hypothesis to test through timings and profiles; not a measured platform conclusion |

Generic `macos-latest` must not be assumed to mean Intel: its actual architecture depends on GitHub's runner mapping and repository availability. The experiment will assert architecture instead of inferring it from a label.

An existing successful upstream Ubuntu release run reports its entire "Build distribution" step between `18:47:29Z` and `18:47:30Z` on 2026-10-23. This is coarse, one-second-resolution context, **not** a precise benchmark or an ARM comparison. It cautions against assuming a large package-build problem before measuring. [Raw job metadata](results/environment/upstream-publish-job.json); [upstream run](https://github.com/fastapi/fastapi/actions/runs/40006169561).

## Controlled experiment

The baseline is the ordinary isolated PDM build. The candidate pre-provisions the same pinned PDM backend and disables repeated build-environment isolation. This is diagnostic, not yet a recommendation to change publishing. It must preserve normalized archive member contents and validate wheel `RECORD` hashes.

Measure package builds separately from dependency provisioning, cache preparation, diagnostic profiling, tests and runner queue time. Alternate baseline/candidate order over repeated trials. Report medians and ranges rather than selecting the fastest trial. A warm dependency cache is not a cold machine. Time saved by pre-provisioning is not free: report its separate cost and whether a single build amortizes it.

Cross-machine comparisons must use the same source, Python patch release, uv version, backend version, artifact scope and cache policy. They describe the measured runners, not Windows versus macOS universally. Single-run parity is not sufficient evidence for a durable speed claim.

## Local provisioning limitation and recovery

`files.pythonhosted.org` fails TLS handshakes in uv, Windows curl and Python's TLS implementation. The observed DNS target is `6.6.0.190`; this observation alone does not establish why the network path fails. PyPI metadata and GitHub downloads are reachable. No certificate checking, DNS configuration or network protection was disabled.

The owned fork `yeelam-gordon/fastapi` is available for requested CI execution because upstream access is read-only. The Windows ARM job will also produce a dependency wheelhouse for ordinary offline local installation. The local [provisioning script](provision.ps1) supports that wheelhouse and verifies the official uv archive digest.

## Next optimization decisions depend on the measured critical path

| If measurements show... | Bounded next action | Correctness boundary |
|---|---|---|
| Isolation dominates repeated builds | Consider a dedicated pinned build-tools environment reused within a job | Retain a clean isolated release check; include bootstrap in total latency |
| Wheel download or source dependency build dominates | Cache by OS/architecture/Python/lock; verify ARM wheel availability before source compilation | Do not remove required dependencies or silently substitute x64 Python |
| File scanning/compression dominates | Profile Python backend and file I/O before changing package traversal or compression | Preserve archive members, metadata and reproducibility |
| Tests dominate after build work | Measure collection, worker startup and per-test durations; sweep a small worker-count set | Preserve test selection, assertions and failures; no blanket `-n auto` promise |
| Windows runner remains slower | Inspect CPU utilization, storage, power mode and runner resources with traces | Do not attribute a platform cause from elapsed time alone |

## Status

Implementation, CI execution and independent verification are in progress. This document will be updated with measured results and verified external sources; it does not yet claim a speedup or parity.
