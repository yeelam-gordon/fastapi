# FastAPI Windows ARM build optimization

## Active continuation: round 2

The user reaffirmed that the goal is Windows at least as fast as Mac, not merely a partial improvement. The current task is reopened. [INVESTIGATION-AND-PROPOSALS.md](../INVESTIGATION-AND-PROPOSALS.md) owns the ranked proposal table and acceptance loop.

### Current priority: matched analysis pipeline

User correction accepted: compare existing Windows/Mac wall durations first,
rank differential critical-path seconds, then collect missing diagnostics.
`performance-method` contains the checked method; `ci-foundation-audit` contains
the actual paired timing/coverage audit. Local Windows hotspots do not establish
the cause of a Windows/Mac gap.

The separate manual `arm-build-diagnostics.yml` is implemented with normal
context and distinct resource/function/import/allocation passes, actual hook
identities and explicit native-coverage gaps. Its instrumented data is never
performance-eligible. Local integrated validation and all four reviewed handoff
fixes passed their bounded gates. `diagnostics\READINESS.md` records approval
for one two-job analysis allocation, used by run 40859922266. Windows artifacts
were retained; Mac stopped before profiling at two defects in our test fixtures.
Both are repaired locally, but Mac collection remains missing. The platform
selector now permits a Mac-only backfill; no additional allocation is approved.
See `diagnostics\analysis-runs\40859922266\RESULT.md`.
The original explicit build-first workload remains the analysis target.
The unidentified dashboard row is excluded from claims, not silently replaced
by package-only results; its separate clarification is not a reason to abandon
the already requested and validated package-build diagnosis.
`MEASUREMENT-BOUNDARIES.md` explains repository preparation, package creation,
aggregate benchmark metrics and the previously confusing word "window".
The bounded public row-definition trace is complete in
`benchmark-row-scope\ROW-DEFINITION.md`: multiple fields/aggregate revisions
exist, but the screenshot's renderer/selector remains unidentified. Its
URL/hyperlink target or exact field/revision is needed before claiming results
for that row. One bounded analysis allocation may use the known build-first
scope was used; no aggregate benchmark reproduction is claimed.
See `diagnostics\ANALYSIS-PLAN.md` and `CONTRACT.md`.

Optimization followups are paused. P25's completed 2.79% local full-build
change failed its advancement gate; no further tuning or CI was started.

### User-directed adoption priority

Shared-toolchain improvements rank first; portable FastAPI best practices rank
second. Bespoke/non-scalable hacks are rejected, and maintainer value and review
burden are mandatory gates. The complete rule is in [GOALS.md](../GOALS.md).
The current FastAPI-specific SDK/private-PDM route is **diagnostic-only**:
its full C: campaign and next CI run are paused pending a credible generalizable
owner-level proposal, even if its technical readiness gates pass.

Workers finish only already-in-flight preparation and tightly coupled cleanup
repairs, retain all evidence and then stop. Do not extend the measurement
framework to pursue this rejected adoption form. Investigate standard-command
bottlenecks and transferable changes next; no upstream PR is authorized.

### Current readiness checkpoint

Parity is still unestablished. Two hosted experiment runs and one analysis
allocation have been used. The SDK campaign below remains parked, not a
prerequisite for more diagnostic-framework work. A proposed Mac-only backfill
needs a new budget decision; local fixture repairs do not authorize a retry.

### Git architecture follow-up

The CI-selected Git entry file is ARM64. The local dynamic probe observed the
real ARM64 Git body launching x64 MSYS shell/utilities: 43 sampled processes,
eight images. Shell/script bytes match the installed CI candidates, but local
VFS Git differs from the CI distribution and live CI descendants remain
unverified. Public packaging sources corroborate the mixed toolchain. This is
not proof that all Git is slow, that emulation explains the measured gap, or
that MDE is responsible. See `git-native-chain\ANSWER-BOUNDARY.md`.

WorkIQ returned technical references kept local/ignored; ADO connections timed
out. Public reports rely on independently cited public sources.

| Gate | State | Evidence / remaining question |
|---|---|---|
| SDK source reuse and unsupported hooks | independently passed | PC-001/PC-002 closed; 29 normal/optimized tests and full artifact oracle |
| Fresh caller lifecycle | earlier real C: smokes passed | Repeat integrated campaign with the final committed wrapper and controller |
| Strict caller receipts and code identities | PP001/PP002 independently closed | Preserve all guards when updating the wrapper argv contract |
| Process-family ownership | native Windows proof passed | Named Job Object and cleanup fixes verified; native Mac and hosted nested-job behavior remain runner-only |
| Explicit caller bytecode policy | CW001 independently closed | `63b17359` passes `-B` explicitly; real interpreter probes confirm effective suppression |
| Actual sparse input deployment | passed locally | Frozen `102ddabc` actual receipts validate 22 inputs and 3,233 canonical source files; C: NTFS placement recorded |
| Wrapper/controller integration | CW002 independently closed | `d339ef22` exact argv repair independently verified against frozen master; lifecycle guards retained |
| Final v4 integration fixtures | bounded independent pass | `VERIFY-V4.md`; native Mac and complete real package campaign remain outside that proof |
| Managed-venv normal process exit | corrected liveness policy independently reviewed | Original failure cause remains unproven; frozen `a44aae95` focused C: gates and genuine offline preparation passed, without a campaign |
| In-flight PC002 cleanup | repaired; lane closed | `6f03951b` attempts all pinned-handle closes and preserves termination/cleanup errors; final focused suite/lint passed; measurement hygiene only |
| Official uv version preflight | repaired and locally exercised | `f17b593b` validates exact 0.13.6 plus structured optional metadata; 17 integrated tests include the verified native executable |
| Full fixed-schedule local campaign | paused by adoption-priority decision | Preserve in-flight preparation/failure evidence; no new campaign for the current bespoke SDK |
| Matched new native ARM CI | gated on a transferable proposal first | Technical readiness alone does not justify spending CI; no automatic retry |

| Current lane | Branch / worktree suffix | Owned output |
|---|---|---|
| Standard uv supported-practice screen (completed; rejected) | `investigate/arm-uv-build-bytecode` / `uv-build-bytecode` | P22 five C: pairs show no meaningful benefit; retain all outputs, no further CI |
| Generic PDM archive prototype (blocked) | `investigate/arm-pdm-archive-io` / `pdm-archive-io` | P23 68-line patch and focused proof/lint pass; owner mypy unavailable after secure TLS attempts, assistance requested; no performance screen |
| Shared pathlib V2 screen (completed; parked) | `investigate/arm-pathlib-relative` / `pathlib-relative` | P25 micro passed, 2.79% full-build change failed advancement gate; preserve artifacts, no more tuning/CI |
| Standard backend codec attribution (completed) | `investigate/arm-compression-attribution` / `compression-attribution` | P20 CRC ~3 ms, raw deflate ~246 ms in one public-sdist profile; no rebuild or gain claim |
| Temporary uv activation files (source triage only) | `investigate/arm-uv-build-activators` / `uv-build-activators` | P24 source fact, not cost attribution or a justified change |
| Controller preflight repair (completed) | `investigate/arm-paired-ci-harness` / `paired-ci-harness` | Exact semantic-version validation with original raw output retained |
| Ownership correction and independent review (completed) | `investigate/arm-process-lifecycle`, `review/arm-process-containment` | Complete owned-member wait states and cleanup repair; original causal uncertainty retained; no further framework work |
| Source-only next proposals (completed) | `investigate/arm-compression-path`, `investigate/arm-sdk-validation-cost` | P20 codec attribution and P21 metadata reuse; no new timed work or readiness requirement |
| Integrated C: readiness (paused) | `investigate/arm-local-paired-readiness` / `local-paired-readiness` | Prepared inputs retained; wait for repaired frozen snapshot and explicit master go |

These are independent preparation/verification lanes. Only the local-readiness lane may run the full C: campaign. Workers do not push, dispatch CI, change security controls or modify the read-only original source worktree. No additional full-agent coordinator is needed.

**Fork budget protection:** two ARM experiment runs, one analysis allocation
and three earlier incidental Ubuntu Conflict detector runs are recorded.
The master disabled **only** `detect-conflicts.yml` in `yeelam-gordon/fastapi`
through the workflow API and verified `disabled_manually`; no upstream workflow
file was changed. No fourth ARM allocation is authorized.

Read-only latest-release checks on 2026-10-29 returned uv **0.13.6** and
pdm-backend **2.5.0**, matching the inspected pins; no tool upgrade was made.

### Earlier isolated-lane history

The research checkpoint is `bfc306726db5727d6a358e85630ced44aa4aa4e2`. Four first isolated lanes completed and were integrated; the next readiness lanes are being established. No additional full-agent coordinator is currently needed.

| Lane | Branch | Worktree under `Generated Files\worktrees` | State |
|---|---|---|---|
| Portable minimal PDM proposal | `investigate/arm-portable-candidate` | `portable-candidate` | integrated: eight tests and strict functional proof; independent code review next |
| Existing runtime distribution control | `investigate/arm-runtime-distribution` | `runtime-distribution` | integrated: no convincing advantage; no pure-PGO claim |
| Independent evidence/attribution review | `review/arm-evidence-attribution` | `evidence-attribution` | integrated: bounded evidence accepted; stale synthesis fixed in master |
| Fair next-benchmark contract | `investigate/arm-benchmark-contract` | `benchmark-contract` | integrated: caller/standard isolation separated; no CI authorization |
| Clean benchmark input, not a worker | `source/fastapi-base-79cab` | `source-fastapi` | read-only original source |

Workers commit only owned paths on their branches and do not push or dispatch CI. The master owns integration. The clean source worktree must be archived/copied before builds; do not write backend state into the shared input tree. This also separates application source from research/evidence/worktree growth.

Worker origin commits: portable `749e211d`, review `cc469129`, protocol `da23ed29`, runtime `6704ea2a`. Integrated master commits retain each worker's scoped changes and co-authorship. [INTERFACES.md](protocol/INTERFACES.md) coordinates the next independent wrapper, harness and code-review lanes.

| Next active lane | Branch / worktree suffix | Owned output |
|---|---|---|
| Independent portable-code review | `review/arm-prefetch-code` / `prefetch-code-review` | `reviews\prefetch-code` |
| Fresh caller-isolation wrapper | `investigate/arm-caller-isolation` / `caller-isolation` | protocol wrapper, lock and focused tests |
| Paired-OS experiment harness | `investigate/arm-paired-ci-harness` / `paired-ci-harness` | versioned measurement/comparison, tests and manual workflow |

These were the initial three readiness lanes. Their component results and subsequent integration findings are summarized in the current checkpoint above. No CI, push or release adoption was delegated.

### Earlier readiness findings

- Independent code review reproduced PC-001 (backend-generated `.pdm-build` state breaks shared-source reuse) and PC-002 (case-variant unsupported hook can execute before rejection). Both were forwarded unchanged and independently reproduced by the producer.
- Producer fix `3c10320c` is committed; independent verification and same-source wrapper smokes are pending. No source-copy workaround or manifest weakening is accepted.
- Harness `73577fc7` passes its fixture/static checks but is not integration-ready by that fact alone; independent protocol review is active in `review/arm-paired-protocol`.
- Targeted LF attributes protect versioned code/locks/oracle identities across Windows/Mac checkout. Raw captured evidence remains byte-preserved.

### Component-gate history

- PC-001 and PC-002 are independently closed: producer origin `3c10320c`, independent fix review `21788c19`; 29 normal/optimized tests and unchanged-manifest shared-source integrations passed. No source-copy workaround was accepted.
- Fresh C: caller readiness passed S1 → S3 → stock B → SDK after that fix. Three SDK environments were unique and removed; all SDK artifacts passed the full oracle. Single readiness invocation walls were 6.421 s (S1), 4.796 s (S3), and 4.952 s (SDK after B)—not a paired performance benchmark or Mac result.
- Paired protocol review `16f0b4a` found PP001 (caller receipt/lifecycle not enforced), PP002 (missing identities accepted), and PP003 (polling ownership limit). Harness producer is fixing the first two; independent process-lifecycle adjudication is evaluating the smallest justified resolution of PP003.
- The next three independent lanes are harness repair, fixed-behavior review preparation and process-lifecycle assessment. No third CI run is authorized by partial fixture success.
- PP001/PP002 producer repair `8a58b8c6` is committed; independent fixed-behavior review is running. PP003 was independently retained as a real timeout-ownership limitation. The master approved a bounded documented job/group containment helper for measurement correctness, not a general supervisor framework or a claimed FastAPI speedup.

| Task | Dependencies | State | Acceptance |
|---|---|---|---|
| round2-overhead | existing canonical input and reference | done | Selective proof retained; ZIP-import follow-up lacked a convincing gain |
| round2-native-archive | existing canonical input and Mac reference | done | Strict Mac equivalence; mode gap closed; 2.223 s insufficient |
| round2-native-backend | existing canonical input and reference | rejected after proof | 1.660 s but incompatible metadata/version behavior |
| round2-integrate | accepted worker evidence | local proof done; optimization continues | 1.700 s median; all Mac contents and execute bits match |
| round3-node-writer | round2-stage attribution | diagnostic proof done; not adopted | Correct artifacts, but higher maintenance than the standard-library proposal |
| round2-verify | round2-integrate | pending | Independent correctness/performance-readiness verdict |
| round2-ci | round2-verify | gated | Only a locally justified, budgeted runner experiment; then inspect and loop |

### Research update: prior art and competing causes

The supplied prior branches were source-audited with pinned revisions and explicit original attribution in [PRIOR-WORK.md](../PRIOR-WORK.md). Their numerical table is not reproduced or mapped to an exact timer. HOBL separates legacy isolated build, modern build, setup and runtime; do not silently substitute one for another.

| Task | State | Acceptance |
|---|---|---|
| standard-frontends-C | done | 13.421 / 9.672 / 5.961 s for current isolated frontends; actual pip/no-ensurepip call path |
| native-toolchain-provenance | done | Published standalone Windows ARM PGO verified; no blanket unoptimized-runtime claim |
| prior-hobl / prior-bootstrap / prior-uvicorn | source audit done | Pinned sources, limits and credit; no foreign-patch performance claim |

The user reaffirmed that expertise requires primary-source research and appropriate tools across interpreter, compiler/configuration, dependency, filesystem and ARM-optimization hypotheses—not a single assumed MDE cause.

Historical round-one evidence below is retained, not an assertion that the overall goal is complete.

## Goal and acceptance

The authoritative targets and acceptance principles are in [GOALS.md](../GOALS.md). Performance parity is a target, not an established result.

Top-level `Generated Files\PERSONA.md` and `GOALS.md` own the task definition. Research, scripts, raw measurements and decisions belong under `Generated Files\arm-build`. The executable GitHub Actions workflow requires a file in `.github\workflows`; it references this independent experiment and does not replace existing CI.

## Expert operating method

The authoritative performance-engineering persona and reasoning/measurement method are in [PERSONA.md](../PERSONA.md). This workboard owns execution state, not those rules.

## Execution graph

Root owns transitions, integration and this workboard. Native parallel tasks; no durable runtime needed. Target 2-3 independently useful active lanes, with a ceiling of 15. Each new investigation/proposal uses an owned branch/worktree. Serialize only real dependencies or interfering measurements. No deadline was specified; tasks are bounded to independently useful investigations or implementation units, with at most two review/fix rounds before reporting unresolved issues.

| Task/revision | Dependencies | State | Acceptance | Output |
|---|---|---|---|---|
| build-audit/r1 | none | done | Source-cited package/CI map and correct build unit | Agent final return; consolidated into FINDINGS.md |
| arm-build-research/r1 | none | done by root after interrupted worker | Primary-source runner/toolchain facts and expert method | SOURCES.md |
| provision/r2 | none | done | Native tools plus official minimal-runtime wheelhouse restored offline; artifact smoke passed | LOCAL-SETUP.md |
| benchmark/r3 | build-audit/r1, provision/r2 | done | Two initial runs plus five-pair canonical-source correction; artifacts checked | results/local-01, local-02, local-03-canonical |
| ci/r2 | build-audit/r1, arm-build-research/r1 | two runs executed; corrected run passed | Real ARM jobs and smokes; shared frozen inputs; strict postprocessing retained | CI.md |
| verify/r3 | benchmark/r3, ci/r2 | done; independent high-confidence evidence verdict | Strict rejection, source fingerprints, arithmetic and 26 tests independently checked | VERIFY.md |
| findings/r3 | all above | current research round delivered; parity unestablished | Measured improvements, strict comparability limits and locally validated next step | FINDINGS.md |

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
- Initial hypothesis: retain PDM and the complete sdist-to-wheel build, but measure a pre-provisioned, pinned backend without repeated build-isolation setup. Later trials demonstrated local and CI build-only improvements; setup-inclusive end-to-end benefit and strict cross-platform parity remain unestablished. Include provisioning separately so savings are not hidden.

## Final evidence and boundaries

- The resume boundary interrupted three agents. Repository audit had returned usable results; the benchmark worker left source/tests that root recovered and integrated. Root completed missing CI implementation and external-source verification directly rather than restarting the same investigations.
- Exploratory result: baseline median 3.8309382 s; candidate 2.8691174 s; seven alternating pairs; all 16 builds passed archive checks. A final audit identified incomplete executed-harness provenance, so a committed/fingerprinted confirmation run was added.
- Confirmation result: baseline median 3.6294956 s; candidate 2.7644276 s; seven alternating pairs; all 16 builds passed archive checks. Executed harness fingerprint matches committed source `248555dc744c6fd74acde93254101ce7ff4484d0`. Confirmed 23.8% lower repeated-build latency, not a proven CI/cold-install improvement.
- Direct PDM function profile passed archive equivalence and attributed 1.659 s to sdist creation and 0.159 s to wheel creation, with profiler overhead. No native compiler workload exists in FastAPI packaging.
- Native Ruff checks/formatting and 11 stdlib tests passed. Independent review caught missing sdist executable-bit comparison and hardware-versus-interpreter architecture checks; both were fixed and independently rechecked.
- Initially Git push lacked noninteractive credentials, then authenticated push was rejected for missing `workflow` scope. The user later completed authorization; no permissions bypass was attempted.
- Corrected CI uses explicit ARM labels, separate provisioning timings, frozen hash locks, seven paired builds, installed-wheel smoke and failure artifacts. Both corrected jobs passed.
- No production FastAPI behavior, package manifest, existing tests or existing workflows changed. No upstream PR was opened.
- User completed workflow authorization; active account and new scope verified. Redundant authentication/dialog helpers were stopped before CI execution.
- Two CI runs were used: `40814042898` passed Windows but failed the native Mac universal-build-tag guard; `40814588064` passed both jobs after local regression/provisioning/build checks.
- Observed corrected medians: Windows 3.129 s to 2.679 s; Mac 0.950 s to 0.730 s. Strict comparison rejected source newline and sdist executable-mode differences; do not call it artifact-identical parity evidence.
- Canonical Git archive bytes were corrected and validated locally with five paired builds. All wheel/sdist member contents then match the Mac reference; five shell-script executable modes still differ. No third CI run is scheduled.
- The Windows wheelhouse restored native build, psutil and minimal runtime tools into a separate local environment; consistency and artifact smoke passed without changing the original measurement environment.
