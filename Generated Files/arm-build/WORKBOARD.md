# FastAPI Windows ARM build optimization

## Active continuation: round 2

The user reaffirmed that the goal is Windows at least as fast as Mac, not merely a partial improvement. The current task is reopened. [INVESTIGATION-AND-PROPOSALS.md](../INVESTIGATION-AND-PROPOSALS.md) owns the ranked proposal table and acceptance loop.

### Current readiness checkpoint

Parity is still unestablished. Exactly two hosted experiment runs have been used; no third run has been dispatched. The next hosted run remains gated on a complete local Windows campaign, not only unit tests or isolated component proofs.

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
| Managed-venv normal process exit | **LOCAL-OWNERSHIP-004 blocks readiness** | Real C: helper test exits 0 but reports `survivors=true`; bounded diagnostics did not reproduce it; original failure remains valid |
| Official uv version preflight | repaired and locally exercised | `f17b593b` validates exact 0.13.6 plus structured optional metadata; 17 integrated tests include the verified native executable |
| Full fixed-schedule local campaign | paused before any samples | Original failures retained; no retries/replacements, fake Mac comparison or performance claim |
| Matched new native ARM CI | gated | Only after local integration and artifact gates pass; no automatic retry |

| Current lane | Branch / worktree suffix | Owned output |
|---|---|---|
| Controller preflight repair (completed) | `investigate/arm-paired-ci-harness` / `paired-ci-harness` | Exact semantic-version validation with original raw output retained |
| Ownership correction and independent review | `investigate/arm-process-lifecycle`, `review/arm-process-containment` | Complete owned-member wait states, not an unsupported inference from job association accounting; causal uncertainty retained |
| Source-only next proposals (completed) | `investigate/arm-compression-path`, `investigate/arm-sdk-validation-cost` | P20 codec attribution and P21 metadata reuse; no new timed work or readiness requirement |
| Integrated C: readiness (paused) | `investigate/arm-local-paired-readiness` / `local-paired-readiness` | Prepared inputs retained; wait for repaired frozen snapshot and explicit master go |

These are independent preparation/verification lanes. Only the local-readiness lane may run the full C: campaign. Workers do not push, dispatch CI, change security controls or modify the read-only original source worktree. No additional full-agent coordinator is needed.

**Fork budget protection:** read-only inspection found two ARM experiment runs and three incidental push-triggered Ubuntu Conflict detector runs. The latter's most recent job lasted about three seconds, but it was still an unnecessary allocation. The master disabled **only** `detect-conflicts.yml` in `yeelam-gordon/fastapi` through the workflow API and verified `disabled_manually`; no upstream workflow file was changed. The manual ARM experiment remains active. No new experiment has been dispatched.

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
