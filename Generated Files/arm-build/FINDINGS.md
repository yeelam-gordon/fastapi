# FastAPI ARM build investigation

## Active continuation

The user reopened the optimization loop: a partial speedup does not meet the goal. The live [investigation/proposal table](../INVESTIGATION-AND-PROPOSALS.md) records current decisions. Round 2 now has an experimental **fully Mac-artifact-equivalent** PDM/native/selective pipeline at **1.700 s median locally**, including correct script executable bits. That resolves the old local permission blocker, not the speed target. Native writer and import investigations continue without another CI run. The sections below retain the completed first-round evidence and its limitations.

## Builds improved; strict Windows/Mac parity is not demonstrated

The corrected [Windows/macOS ARM CI experiment passed both jobs](https://github.com/yeelam-gordon/fastapi/actions/runs/40814588064). Removing repeated PDM isolation reduced the observed Windows build time **14.4%**. Its optimized median was **3.67 times** the Mac median, but strict cross-platform validation rejected the comparison because source line endings and sdist executable modes differed. **The requested parity target is not demonstrated.** The current evidence also cannot establish physical 20-core Windows versus 16-core Mac performance.

| Complete warm-cache package build | Windows 11 ARM64 | macOS ARM64 |
|---|---:|---:|
| Runner logical CPUs | 4 | 3, virtual Apple M1 |
| Isolated PDM median, seven trials | 3.129 s | 0.950 s |
| Dedicated backend median, seven trials | 2.679 s | 0.730 s |
| Lower median from isolation removal | 14.4% | 23.2% |

Both use source `264cbad400c8336057a70b9b6a65bfdb4920321e`, native CPython 3.13.15 from the same managed distribution family, uv 0.13.6 and PDM 2.5.0. All measured trials were offline after cache preparation. Each platform's artifacts passed its baseline equivalence checks and installed-wheel smoke. [Windows report](results/ci-40814588064/windows/ci/report.json), [Mac report](results/ci-40814588064/macos/ci/report.json).

**These are observed timings, not an accepted artifact-identical platform benchmark.** The postprocessor preserved its rejection instead of silently normalizing package content or permissions. [Strict comparison diagnostics](results/ci-40814588064/comparison-r2.json).

Python provisioning was another concrete improvement: the first Windows `setup-python` step took **124 seconds** at GitHub's coarse timestamp resolution; the corrected managed-Python install, discovery, environment creation and probe total **4.46 seconds**, with the actual download/install phase at **3.51 seconds**. These are observations from two differently configured jobs, not a paired cold-provisioning benchmark. Package-build medians exclude this work. [First-run step timings](results/ci-40814042898/jobs.json), [corrected setup receipt](results/ci-40814588064/windows/bootstrap/python-setup.json).

## Local confirmation: 23.8% lower repeated-build latency

On this Windows ARM VM, the complete warm-cache package build fell from **3.629 s to 2.764 s median** across seven alternating trials per variant, a **23.8% reduction** in the committed-harness confirmation run. All 16 builds (two preparations plus 14 timed builds) produced equivalent normalized sdist/wheel contents with valid wheel `RECORD` hashes and preserved sdist executable bits. This is a build-only result after backend provisioning, not a cold-install or end-to-end CI speedup. [Confirmation report](results/local-02/report.json).

FastAPI builds a pure-Python distribution, not a native executable. Adding compiler workers cannot accelerate compilation that does not exist. The measured candidate retains PDM, the source distribution and the wheel built from that source distribution; it avoids repeated build-environment isolation using a dedicated pre-provisioned backend.

The local machine is a 16-core Cobalt 100 Windows ARM64 VM, not the eventual approximately 20-core physical Windows machine. Native CPython 3.13.15 works. Verified official ARM64 uv 0.13.6 and Ruff 0.17.3 are installed locally. PDM 2.5.0 was self-built from its verified official GitHub revision because PyPI wheel transport is blocked. Standard-library profiling was executed; Windows Performance Recorder and Analyzer are present.

| Variant | Median | Observed range | Scope |
|---|---:|---:|---|
| Isolated PDM baseline | 3.629 s | 3.571-3.684 s | Default complete `uv build`, warmed local backend wheel cache |
| Dedicated backend, no repeated isolation | 2.764 s | 2.660-2.867 s | Same Python, PDM version, source snapshot and archive verification |

This saves about **0.865 s per repeated build** on this host. The first, exploratory run independently observed 3.831 s to 2.869 s (25.1% lower), but has the harness-provenance limitation below; it is retained rather than selected as the headline. [Exploratory report](results/local-01/report.json). The comparison excludes backend acquisition/installation, and a single release build may not repay that bootstrap cost. Preparation builds also used a pre-downloaded local wheelhouse and are **not** cold dependency-install measurements. The CI-exported wheelhouse subsequently restored the complete native tool/minimal-runtime environment locally; an installed-FastAPI smoke check passed. The full repository test suite was not run.

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

## Comparability correction was validated locally, without a third CI run

The two runners used the same Git commit but `git archive` applied checkout line-ending conversion: the Windows archive contained CRLF, while the Mac archive contained LF. This produced 58 differing wheel-content members and 1,080 differing sdist-content members. Five shell scripts also lost executable bits in the Windows-produced sdist. Those differences are distinct from the harness-file CRLF difference, which the postprocessor now validates by raw SHA256 before normalizing only source-file newline encoding.

The harness now explicitly uses `git -c core.autocrlf=false archive` and records canonical source-file hashes and Git archive permission bits. A local reproduction verifies that this archive matches canonical Git blob bytes. [Source-byte proof](results/environment/source-newline-validation.json).

A third **local**, five-pair experiment used those canonical bytes at the same package-source commit as CI. Its wheel members and all sdist member contents match the retained Mac reference; only the five executable-mode differences remain. No permission differences were waived. [Canonical artifact diagnostics](results/environment/canonical-artifact-diagnostics.json), [local report](results/local-03-canonical/report.json). This corrects a measurement flaw without spending another CI run, but does not retroactively validate the earlier CI comparison or resolve the cross-platform sdist permission policy.

## Profiling explains why core count is not the first lever

The separate PDM function profile attributes **1.659 s to source-distribution creation and 0.159 s to wheel creation**. These profiled durations include instrumentation overhead and exclude uv orchestration, sdist extraction and other subprocess startup; they are not additive substitutes for the benchmark medians. Source-distribution work processes about 1,269 files; file opening, tar construction and compression are material components, with `zlib.compress` accounting for 0.221 s in that diagnostic. The measured package work is primarily serial Python/filesystem processing, not a compiler farm. [Profile result](results/profile-01/profile.json), [sdist functions](results/profile-01/sdist.txt), [wheel functions](results/profile-01/wheel.txt).

Prioritize avoiding repeated setup and unnecessary builds, then investigate file traversal and storage. Do not remove tests/examples from the sdist, change compression or swap backends just to win a benchmark without an explicitly accepted artifact/compatibility requirement. For real native dependency builds, ARM64 wheel availability and compiler parallelism are separate follow-on investigations.

## Provisioning recovery and CI execution

`files.pythonhosted.org` fails TLS handshakes in uv, Windows curl and Python's TLS implementation. The observed DNS target is `6.6.0.190`; this observation alone does not establish why the network path fails. PyPI metadata and GitHub downloads are reachable. No certificate checking, DNS configuration or network protection was disabled.

Local recovery did not require weakening transport: the official PDM repository declares an empty build requirement list and an in-tree backend. Its tag `2.5.0` resolved to `8c6653726f71afdb2059b44dc9c7706693e95be6`; uv self-built it without network dependencies, and the resulting wheel provisioned both variants. This locally built backend wheel is **not represented as the official PyPI wheel**. Backend/source/tool provenance and reproduction are recorded in [LOCAL-SETUP.md](LOCAL-SETUP.md).

The owned public fork [yeelam-gordon/fastapi](https://github.com/yeelam-gordon/fastapi) hosts this independent experiment; upstream is untouched. The initial missing OAuth scope was resolved by the user's authorization. The first run passed Windows but failed macOS because our guard rejected a valid native `universal2` build tag. The corrected guard distinguishes native ARM runtime from Rosetta, and a regression test covers this case.

The second run passed both jobs after local tests, static checks and managed-Python setup/build validation. Tool and minimal-runtime locks generated by the first resolver job were frozen before the second run, so both jobs use the same committed inputs rather than independently resolving newer dependencies. The Windows-only wheelhouse export is experiment overhead for local recovery; it is not included in build-only medians or used as a like-for-like bootstrap comparison.

Exactly **two CI runs** were dispatched in this round; no further run is scheduled. [CI.md](CI.md) records evidence and reproduction. GitHub documents the selected public Windows runner as 4 CPUs/16 GB RAM and Mac as 3 M1 CPUs/7 GB RAM; they are not equal-resource or physical comparison machines. [Verified sources](SOURCES.md).

## Next optimization decisions depend on the measured critical path

| If measurements show... | Bounded next action | Correctness boundary |
|---|---|---|
| Isolation dominates repeated builds | Consider a dedicated pinned build-tools environment reused within a job | Retain a clean isolated release check; include bootstrap in total latency |
| Wheel download or source dependency build dominates | Cache by OS/architecture/Python/lock; verify ARM wheel availability before source compilation | Do not remove required dependencies or silently substitute x64 Python |
| File scanning/compression dominates | Profile Python backend and file I/O before changing package traversal or compression | Preserve archive members, metadata and reproducibility |
| Tests dominate after build work | Measure collection, worker startup and per-test durations; sweep a small worker-count set | Preserve test selection, assertions and failures; no blanket `-n auto` promise |
| Windows runner remains slower | Inspect CPU utilization, storage, power mode and runner resources with traces | Do not attribute a platform cause from elapsed time alone |

## Delivery and limits

Local and CI improvements are measured, and both CI artifact smokes passed. No FastAPI source, dependency requirements, existing release workflow or test selection was changed. The experiment branch is published only on the owned fork; upstream CI is untouched. Independent verification found and corrected executable-bit comparison and interpreter-architecture checks; actual CI also exposed universal-build-tag handling. Final verification state is owned by the workboard.

The strict Windows-versus-Mac parity target remains unestablished, and physical-device performance is unmeasured. Using the observed numbers only, Windows would need roughly **72.7% further reduction** from its optimized build time to match this Mac sample; removing isolation alone is nowhere near enough. That estimate is not a validated apples-to-apples target while artifact differences remain. The local profile identifies serial package/file work, not the cause of the remote gap. Resolve the permission/comparability decision and validate the next hypothesis locally before spending more CI capacity; see [NEXT-EXPERIMENTS.md](NEXT-EXPERIMENTS.md).
