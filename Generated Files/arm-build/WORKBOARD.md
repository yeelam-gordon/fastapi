# FastAPI Windows ARM build optimization

## Goal and acceptance

Help the maintainer choose changes that reduce real FastAPI build latency without changing package contents or runtime behavior. The target is Windows 11 ARM64 build time at or below macOS ARM64, first in GitHub CI and ultimately on physical hardware. Performance parity is a target, not an established result.

All task research, scripts, raw measurements and decisions belong under `Generated Files\arm-build`. An executable GitHub Actions workflow may require a file in `.github\workflows`; it will reference the experiment here and will not replace existing CI.

## Expert operating method

Define the artifact and timing boundary before optimizing. Separate tool provisioning, dependency resolution/download, environment creation, package build, artifact verification and tests. Verify native ARM64 execution. Inspect the critical path before proposing parallelism; extra cores help only parallel work. Compare repeated matched workloads, report cache state and dispersion, preserve failures and validate equivalent artifacts. Distinguish measurements, sourced facts, hypotheses and untested proposals.

## Execution graph

Root owns transitions, integration and this workboard. Native parallel tasks; no durable runtime needed. Maximum useful active workers: 3 (repository audit, external research, later implementation or verification). No deadline was specified; tasks are bounded to independently useful investigations or implementation units, with at most two review/fix rounds before reporting unresolved issues.

| Task/revision | Dependencies | State | Acceptance | Output |
|---|---|---|---|---|
| build-audit/r1 | none | done | Source-cited package/CI map and correct build unit | Agent final return; consolidated into FINDINGS.md |
| arm-build-research/r1 | none | running | Primary-source runner/toolchain facts and expert method | Agent final return; consolidated into FINDINGS.md |
| provision/r1 | none | running | Executable native ARM64 Python and minimal profiling/build tools | environment evidence and local measurements |
| benchmark/r1 | build-audit/r1, provision/r1 | implementation running; execution awaits tools | Repeated baseline/candidate measurements and artifact equivalence | scripts and results |
| ci/r1 | build-audit/r1, arm-build-research/r1 | implementation running; labels being verified | Matched ARM runners, explicit timings, artifacts; dispatch if authorized | Workflow and CI evidence |
| verify/r1 | benchmark/r1, ci/r1 | pending | Independent review, relevant checks, no unsupported performance claims | Verification evidence |
| findings/r1 | all above | pending | Actionable sourced outcome, exact limits and reproduction | FINDINGS.md |

## Initial evidence

- Initial worktree was clean.
- Host reports native ARM64 OS and process, Cobalt 100, 16 physical/logical cores. This is not the proposed 20-core physical comparison machine.
- GitHub account `yeelam-gordon` is active. Repository permissions and fork capability have not yet been established.
- `uv`, `python`, `python3`, `py` and `winget` command names resolve, but resolution alone does not establish that executables work. The initial `uv --version` failed before Python probes ran.

## Confirmed decisions and blockers

- Repository audit: FastAPI uses PDM's pure-Python package backend; there is no native FastAPI compilation to parallelize. Release command is `uv build`. Treat dependency provisioning and tests as separate costs.
- Existing CPython 3.13.15 is native ARM64 and executable. Repository default Python is 3.11; every experiment explicitly selects 3.13.
- Installed verified official uv 0.13.6 ARM64 under `tools`. Created isolated `.venv`; tooling resolution succeeded but wheel installation is blocked by TLS handshake failures to `files.pythonhosted.org` in uv, curl and Python. DNS resolves its Fastly target to `6.6.0.190`. No TLS verification was disabled and no network controls were changed.
- Upstream access is READ; created owned public fork `yeelam-gordon/fastapi` (ADMIN) without changing remotes. Its Actions are enabled. The requested CI experiment will run there, not alter upstream CI.
- CI will produce an ARM64 Windows wheelhouse as well as comparison evidence, allowing reproducible local offline provisioning through ordinary GitHub artifacts.
- Primary candidate: retain PDM and the complete sdist-to-wheel build, but measure a pre-provisioned, pinned backend without repeated build-isolation setup. It is an experiment, not yet a demonstrated improvement. Include provisioning separately so savings are not hidden.
