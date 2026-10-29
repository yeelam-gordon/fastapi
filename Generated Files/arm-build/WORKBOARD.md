# FastAPI Windows ARM build optimization

## Goal and acceptance

The authoritative targets and acceptance principles are in [GOALS.md](../GOALS.md). Performance parity is a target, not an established result.

Top-level `Generated Files\PERSONA.md` and `GOALS.md` own the task definition. Research, scripts, raw measurements and decisions belong under `Generated Files\arm-build`. The executable GitHub Actions workflow requires a file in `.github\workflows`; it references this independent experiment and does not replace existing CI.

## Expert operating method

The authoritative performance-engineering persona and reasoning/measurement method are in [PERSONA.md](../PERSONA.md). This workboard owns execution state, not those rules.

## Execution graph

Root owns transitions, integration and this workboard. Native parallel tasks; no durable runtime needed. Maximum useful active workers: 3 (repository audit, external research, later implementation or verification). No deadline was specified; tasks are bounded to independently useful investigations or implementation units, with at most two review/fix rounds before reporting unresolved issues.

| Task/revision | Dependencies | State | Acceptance | Output |
|---|---|---|---|---|
| build-audit/r1 | none | done | Source-cited package/CI map and correct build unit | Agent final return; consolidated into FINDINGS.md |
| arm-build-research/r1 | none | done by root after interrupted worker | Primary-source runner/toolchain facts and expert method | SOURCES.md |
| provision/r1 | none | done for benchmark/profiling; full PyPI tool suite blocked | Executable native ARM64 Python, uv, PDM, Ruff and standard-library profiler | LOCAL-SETUP.md; host evidence |
| benchmark/r2 | build-audit/r1, provision/r1 | done | Seven baseline/candidate trials in each of two runs; final harness fingerprint matches committed source | results/local-02; confirmed 23.8% lower median locally |
| ci/r1 | build-audit/r1, arm-build-research/r1 | authorized; dispatching after initial scope blocker | Matched ARM jobs with shared inputs and evidence | CI.md |
| verify/r2 | benchmark/r1, ci/r1 | local verification done; CI execution unverified | Independent benchmark PASS/high; architecture/style fixes PASS/high; CI readiness medium because unrun | VERIFY.md |
| findings/r2 | all above | final evidence audit; CI blocked explicitly | Actionable sourced outcome, exact limits and reproduction | FINDINGS.md |

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
- Initial hypothesis: retain PDM and the complete sdist-to-wheel build, but measure a pre-provisioned, pinned backend without repeated build-isolation setup. The later trials demonstrated a local repeated-build improvement; CI/end-to-end benefit remains unproven. Include provisioning separately so savings are not hidden.

## Final evidence and boundaries

- The resume boundary interrupted three agents. Repository audit had returned usable results; the benchmark worker left source/tests that root recovered and integrated. Root completed missing CI implementation and external-source verification directly rather than restarting the same investigations.
- Exploratory result: baseline median 3.8309382 s; candidate 2.8691174 s; seven alternating pairs; all 16 builds passed archive checks. A final audit identified incomplete executed-harness provenance, so a committed/fingerprinted confirmation run was added.
- Confirmation result: baseline median 3.6294956 s; candidate 2.7644276 s; seven alternating pairs; all 16 builds passed archive checks. Executed harness fingerprint matches committed source `248555dc744c6fd74acde93254101ce7ff4484d0`. Confirmed 23.8% lower repeated-build latency, not a proven CI/cold-install improvement.
- Direct PDM function profile passed archive equivalence and attributed 1.659 s to sdist creation and 0.159 s to wheel creation, with profiler overhead. No native compiler workload exists in FastAPI packaging.
- Native Ruff checks/formatting and 11 stdlib tests passed. Independent review caught missing sdist executable-bit comparison and hardware-versus-interpreter architecture checks; both were fixed and independently rechecked.
- Fork creation succeeded. Git push first lacked noninteractive credentials, then succeeded in authenticating through gh but was rejected for missing OAuth `workflow` scope. No remote experiment branch, workflow or run exists. User unavailable to authorize; no permissions bypass attempted.
- Prepared CI has real ARM labels/explicit interpreter checks, separate provisioning timings, shared hash locks, seven paired builds, installed-wheel smoke and failure artifacts. Its execution remains unverified.
- No production FastAPI behavior, package manifest, existing tests or existing workflows changed. No upstream PR was opened.
- User completed workflow authorization; active account and new scope verified. Redundant authentication/dialog helpers were stopped. CI execution can now proceed.
