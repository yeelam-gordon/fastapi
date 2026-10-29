# FastAPI ARM build investigation

## Confirmed result: 23.8% lower repeated-build latency locally

On this Windows ARM VM, the complete warm-cache package build fell from **3.629 s to 2.764 s median** across seven alternating trials per variant, a **23.8% reduction** in the committed-harness confirmation run. All 16 builds (two preparations plus 14 timed builds) produced equivalent normalized sdist/wheel contents with valid wheel `RECORD` hashes and preserved sdist executable bits. This is a build-only result after backend provisioning, not a cold-install or end-to-end CI speedup. [Confirmation report](results/local-02/report.json).

FastAPI builds a pure-Python distribution, not a native executable. Adding compiler workers cannot accelerate compilation that does not exist. The measured candidate retains PDM, the source distribution and the wheel built from that source distribution; it avoids repeated build-environment isolation using a dedicated pre-provisioned backend. Windows/macOS parity remains **unproven** pending CI measurements. The initial workflow-scope blocker is now resolved through the user's authorization.

The local machine is a 16-core Cobalt 100 Windows ARM64 VM, not the eventual approximately 20-core physical Windows machine. Native CPython 3.13.15 works. Verified official ARM64 uv 0.13.6 and Ruff 0.17.3 are installed locally. PDM 2.5.0 was self-built from its verified official GitHub revision because PyPI wheel transport is blocked. Standard-library profiling was executed; Windows Performance Recorder and Analyzer are present.

| Variant | Median | Observed range | Scope |
|---|---:|---:|---|
| Isolated PDM baseline | 3.629 s | 3.571-3.684 s | Default complete `uv build`, warmed local backend wheel cache |
| Dedicated backend, no repeated isolation | 2.764 s | 2.660-2.867 s | Same Python, PDM version, source snapshot and archive verification |

This saves about **0.865 s per repeated build** on this host. The first, exploratory run independently observed 3.831 s to 2.869 s (25.1% lower), but has the harness-provenance limitation below; it is retained rather than selected as the headline. [Exploratory report](results/local-01/report.json). The comparison excludes backend acquisition/installation, and a single release build may not repay that bootstrap cost. Preparation builds also used a pre-downloaded local wheelhouse and are **not** cold dependency-install measurements. No full test suite or installed-FastAPI runtime smoke check ran locally: the required PyPI wheels remain unavailable.

## Scope and evidence

The FastAPI base revision is `79cab5bed28b24d92c185d236feb33f5783dfeb3`. The exploratory snapshot is local commit `cb9309673c4c06f71cae4fbc4461ba783ff91b49`, which adds experiment files but changes no FastAPI package source. That run executed a locally modified harness while Ruff formatting ran in parallel; the recorded dirty status is retained, and its exact executed harness bytes were not separately captured.

The confirmation run uses committed snapshot `248555dc744c6fd74acde93254101ce7ff4484d0`, again without package-source changes. It saves the executed harness bytes and SHA256; that fingerprint was checked against `git show` of the same commit and matched. No edits or formatting were performed during this confirmation run. Top-level [GOALS.md](../GOALS.md) and [PERSONA.md](../PERSONA.md) own the task definition; the [workboard](WORKBOARD.md) owns execution state. Initial host inventory (not the measured source revision) is in [host.json](results/environment/host.json).

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

The baseline is the ordinary isolated PDM build. The candidate pre-provisions the same pinned PDM backend and disables repeated build-environment isolation. This is diagnostic, not yet a recommendation to change publishing. Normalized archive member contents, sdist executable bits and wheel `RECORD` hashes were checked on every build.

Measure package builds separately from dependency provisioning, cache preparation, diagnostic profiling, tests and runner queue time. Alternate baseline/candidate order over repeated trials. Report medians and ranges rather than selecting the fastest trial. A warm dependency cache is not a cold machine. Time saved by pre-provisioning is not free: report its separate cost and whether a single build amortizes it.

Cross-machine comparisons must use the same source, Python patch release, uv version, backend version, artifact scope and cache policy. They describe the measured runners, not Windows versus macOS universally. Single-run parity is not sufficient evidence for a durable speed claim.

## Profiling explains why core count is not the first lever

The separate PDM function profile attributes **1.659 s to source-distribution creation and 0.159 s to wheel creation**. These profiled durations include instrumentation overhead and exclude uv orchestration, sdist extraction and other subprocess startup; they are not additive substitutes for the benchmark medians. Source-distribution work processes about 1,269 files; file opening, tar construction and compression are material components, with `zlib.compress` accounting for 0.221 s in that diagnostic. The measured package work is primarily serial Python/filesystem processing, not a compiler farm. [Profile result](results/profile-01/profile.json), [sdist functions](results/profile-01/sdist.txt), [wheel functions](results/profile-01/wheel.txt).

Prioritize avoiding repeated setup and unnecessary builds, then investigate file traversal and storage. Do not remove tests/examples from the sdist, change compression or swap backends just to win a benchmark without an explicitly accepted artifact/compatibility requirement. For real native dependency builds, ARM64 wheel availability and compiler parallelism are separate follow-on investigations.

## Provisioning recovery worked; CI authorization remains blocked

`files.pythonhosted.org` fails TLS handshakes in uv, Windows curl and Python's TLS implementation. The observed DNS target is `6.6.0.190`; this observation alone does not establish why the network path fails. PyPI metadata and GitHub downloads are reachable. No certificate checking, DNS configuration or network protection was disabled.

Local recovery did not require weakening transport: the official PDM repository declares an empty build requirement list and an in-tree backend. Its tag `2.5.0` resolved to `8c6653726f71afdb2059b44dc9c7706693e95be6`; uv self-built it without network dependencies, and the resulting wheel provisioned both variants. This locally built backend wheel is **not represented as the official PyPI wheel**. Backend/source/tool provenance and reproduction are recorded in [LOCAL-SETUP.md](LOCAL-SETUP.md).

The owned public fork [yeelam-gordon/fastapi](https://github.com/yeelam-gordon/fastapi) exists because upstream access is read-only. The workflow explicitly targets `windows-11-arm` and `macos-15`, CPython 3.13.15 ARM64 and uv 0.13.6. A shared resolver job distributes identical hash-locked tool/runtime inputs, then each platform measures builds and an installed-wheel smoke check. The Windows job also exports a wheelhouse. **None of these jobs has run.** Authenticated push was rejected before a remote experiment branch or workflow was created.

After interactive authorization, use the commands in [CI.md](CI.md). Do not treat preparation of a workflow as performance evidence. GitHub documents the selected public Windows runner as 4 CPUs/16 GB RAM and the Mac runner as 3 M1 CPUs/7 GB RAM; record actual metadata and compare workloads rather than declaring equal hardware. [Verified sources](SOURCES.md).

## Next optimization decisions depend on the measured critical path

| If measurements show... | Bounded next action | Correctness boundary |
|---|---|---|
| Isolation dominates repeated builds | Consider a dedicated pinned build-tools environment reused within a job | Retain a clean isolated release check; include bootstrap in total latency |
| Wheel download or source dependency build dominates | Cache by OS/architecture/Python/lock; verify ARM wheel availability before source compilation | Do not remove required dependencies or silently substitute x64 Python |
| File scanning/compression dominates | Profile Python backend and file I/O before changing package traversal or compression | Preserve archive members, metadata and reproducibility |
| Tests dominate after build work | Measure collection, worker startup and per-test durations; sweep a small worker-count set | Preserve test selection, assertions and failures; no blanket `-n auto` promise |
| Windows runner remains slower | Inspect CPU utilization, storage, power mode and runner resources with traces | Do not attribute a platform cause from elapsed time alone |

## Delivery and limits

The local improvement and unchanged package contents are measured. No FastAPI source, dependency requirements, existing release workflow or test selection was changed. The experiment is isolated on a local branch; upstream CI is untouched. Independent verification found and corrected executable-bit comparison and interpreter-architecture checks; final verification state is owned by the workboard.

The requested Windows-versus-Mac and physical-machine goals remain open. The next required evidence is an authorized CI run, followed by the same experiment on physical ARM devices. Do not promote the no-isolation candidate into publishing until its bootstrap-adjusted benefit and clean-release correctness are established.
