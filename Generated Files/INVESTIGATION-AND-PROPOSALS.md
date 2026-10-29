# Optimization loop: Windows ARM must match or beat Mac ARM

**Status: active; the goal is not reached.** Partial speedups are evidence, not completion. Continue investigation, proposals, local proof and independent verification; spend additional fork CI capacity only after the readiness gate passes.

## Acceptance target

Keep the complete FastAPI source-distribution-to-wheel workload and accepted package semantics. The historical Mac reference is 0.730 s median, but the earlier cross-platform comparison was rejected. That number is only an initial screening reference—not a permanently frozen finish line. Evaluate applicable common optimizations on both platforms; compare best validated configurations and report their ratio. A new accepted comparison must use canonical input bytes and preserve all required executable modes.

Local timing is a screening tool, not proof that the hosted runner meets parity. Physical-device parity remains a separate goal.

## Adoption priority: ecosystem value before benchmark wins

The ranking and mandatory maintainer gate are owned by [GOALS.md](GOALS.md).
This table ranks adoption routes, not evidence strength or claimed speedups.

| Priority | Proposal route / existing evidence | Current disposition | Maintainer-facing gate |
|---|---|---|---|
| **1 — shared toolchain** | Generic I/O and bounded read-prefetch inside PDM, following mechanism evidence from P1/P5/P6/P11/P18 and owner-level P23 | One small generic prototype under review; owner typing is blocked and cross-project/full-command gain remains unproven | Preserve hooks, layouts, errors and streaming without FastAPI-specific lists or private cross-package patches; no adoption on prototype timings |
| **1 — shared toolchain** | Profile-backed pathlib allocation path, P25, inside CPython itself | V1 rejected on equal/fallback cost despite deep-path gains; one distinct small default-case revision under semantic proof only | Preserve public path/subclass semantics and measure all fallbacks; no runtime fork or FastAPI monkeypatch as adoption |
| **1 — shared toolchain** | Codec/build-recipe differences in P20; credited pip/ensurepip prior art in P15/P16 when its workload applies | P20 diagnostic only; no custom runtime justified. Prior work remains credited and is off the observed package-build path | Demonstrate a relevant critical-path cost and supported, maintainable fix; do not infer benefit from architecture labels |
| **2 — portable best practice** | Supported frontend/installer choices in P13, native ARM tooling and reproducible inputs | Existing capability; release already uses uv, so no new FastAPI change is justified merely to claim it | Small supported configuration, reusable guidance and honest attribution; separate setup/build metrics and test Mac too |
| **Rejected form — not a lower-priority queue** | Custom archive/backend adapters, Node writer and FastAPI-specific SDK/private-PDM integration in P2/P3/P7/P8/P18; SDK-only overhead tuning in P21 | Preserve diagnostics; **do not recommend adoption or spend more CI on these forms** | Reconsider only a genuinely general, simpler owner-level change; renaming or wrapping the prototype does not make it transferable |
| **Rejected/deferred for insufficient value** | Dependency ZIP/cache complexity, tiny native extraction and attribute-skipping gains in P9/P10/P12 | Existing rejection retained | A maintainable, material benefit would need new evidence, not more tuning of the same bespoke mechanism |

**Current execution priority: matched diagnosis before more optimization.**
The paired-log audit now establishes a 2.178 s observed isolated-build gap and
1.949 s gap without isolation, but actual backend-hook timings are missing.
Checkout/auth is a separate CI-latency lead: six `foreach` windows contain
8.103 s paired interval difference, not proven Git CPU or shell time.
The [analysis plan](arm-build/diagnostics/ANALYSIS-PLAN.md) and separate manual
diagnostic workflow fill declared coverage gaps; local integration and
independent review gate any new CI allocation. Instrumented data is not
performance proof. No new optimization or official performance run is authorized.
The bespoke SDK stays diagnostic-only. P22 was rejected; P23 typing is externally
blocked; P25's 2.79% local full-build change failed its advancement gate and is
parked. Parity and underlying cross-platform causes remain unproven.

## Investigation evidence ledger

IDs stay stable below; their historical timings do not override the adoption
ranking. A mechanism inferred from a prototype is not yet a portable fix.

| ID | Investigation and current evidence | Proposal to test | Local acceptance gate | Owner / state |
|---|---|---|---|---|
| P1 | One-process full native extraction: 2.541 s in paired local trials; Python extraction and log suppression did not help | Keep fresh-process orchestration; investigate expensive PDM imports rather than site initialization (only about 5 ms difference locally) | Include all imports and build work; no project metadata cache | `windows-critical-path` / completed; ZIP follow-up rejected in P9 |
| P2 | Native mtree preserves all Mac member contents and executable bits; full pipeline 2.277 s, improved to 2.223 s using source permission JSON | Retain mode-correct native serialization as a correctness building block, not a sufficient speed solution | Fresh metadata; strict Mac artifact equivalence; no mode waiver | `native-archive-probe` / correctness accepted; speed insufficient |
| P3 | Bundled native backend: 1.660 s, unsupported existing dynamic version; altered metadata and extra sdist member | Reject this migration as a drop-in optimization; keep PDM metadata/selection | Exact compatibility differences retained; no fast-but-incompatible claim | `native-backend-probe` / rejected |
| P4 | Same Git commit produced different archive newlines; canonical source correction now matches all member contents locally | Retain explicit canonical Git archive bytes and source fingerprint in every subsequent experiment | Independent source-byte checks; no cross-platform source conversion; no waived script-mode differences | Root / implemented; mode correction proved by P2 |
| P5 | Compiler worker count cannot accelerate pure-Python packaging | Pursue parallel archive/file processing only if profiling and a prototype demonstrate benefit | Count all startup/work; do not omit source files or change formats; reject complexity without measured gain | Root / contingent on P1-P3 |
| P6 | Archive-derived selection extracts 64/1269 files; complete sdist retained. Measured 1.954 s versus paired full-extraction 2.541 s | Keep bounded fail-closed selection; combine with P2 | All 60 initial/matrix builds passed same-host checks; configuration edge-case tests still needed | `windows-critical-path` / local improvement accepted |
| P7 | Combined P2 + P6: **1.700 s** median, five trials; all artifacts strictly match the Mac reference, including executable bits | Use as the correct integrated baseline for the next loop | Preserve fresh metadata and full-process timing; not yet below 0.730 s | Root / integrated; speed target missed |
| P8 | Native ARM64 Node writer reaches 1.454 s on Q:, with strict Mac equivalence and four format tests; still above historical Mac | Retain as a diagnostic; do not adopt custom archive-format code for a small shared gain | High maintenance cost; must beat simpler approaches materially on protected C: and evaluate Mac benefit | `node-archive-prototype` / proof complete; adoption gated |
| P9 | Installed 1.973 s, source ZIP 2.008 s, precompiled ZIP 1.923 s; 18 artifact checks passed. About 2.5% gain is noisy and provisioning costs 0.176 s | Reject as an adopted optimization for now; avoid adding dependency-packaging complexity without a repeatable import benefit | No project metadata cache; tool identity/ABI and provisioning cost recorded | `windows-critical-path` / measured; insufficient evidence of value |
| P10 | Native selective extraction: 1.636 s versus paired Python extraction 1.645 s; all artifacts correct | Reject the extra process/adapter complexity for a roughly 0.5% local gain | Small effect, shared-platform potential, no demonstrated meaningful advantage | Root / measured; rejected |
| P11 | Controlled C: follow-up: real uv no-isolation 5.014 s; corrected writer full 6.275 s versus selective 3.300 s. The old 7 s sdist stall did not recur | Keep the extraction result; do not attribute the earlier regression to selection or Defender | Same writer/source policy in the controlled pair; profile locates many opens, not scanner ownership | `protected-c-drive-experiment` / completed |
| P12 | Guarded temporary attribute skipping removed 64 chmod + 64 utime events; only about 0.037 s median beyond prefetch | Do not enable by default for a small incremental gain; retain evidence | Final modes/payloads passed; audit events are not scan counts | `stdlib-file-operations` / measured; deferred |
| P13 | Current isolated C: frontends: build/pip 13.421 s, build/uv installer 9.672 s, uv 5.961 s | Prefer existing supported configuration before custom tooling; release already uses uv, so do not claim a new repo fix | Isolation remains timed; current pip installer uses `--no-compile` and no ensurepip | `standard-frontend-controls` / completed |
| P14 | Published standalone ARM64 artifacts verified: Windows PGO; Mac PGO+LTO. Stock MSI-wrapper defaults are a different case | Do not rebuild on a blanket “unoptimized Windows” premise; collect exact runtime receipts and CPU-stage evidence | Windows `pgo` label does not mean no LTCG; SIMD and causal compiler effects remain unverified | `native-toolchain-audit` / source/artifact audit done; causal claim rejected |
| P15 | Prior pip branch implements Windows-only threaded bytecode compilation, but the inspected build frontend passes `--no-compile` | Keep as credited setup/install prior art; do not apply blindly to the current package-build timer | Reconsider only if the chosen workload actually compiles bytecode during pip install | Prior art / source-reviewed; off current timed path |
| P16 | Prior ensurepip hardlink POC targets 3.12; current outer-pip build path does not call ensurepip | Keep as credited bootstrap prior art, not a package-build explanation here | Verify workload/version first; same-volume/fallback/read-only tests if relevant | Prior art / source-reviewed; off current timed path |
| P17 | Prior Uvicorn changes alter Windows reload shutdown/dedup, not package building | Keep as credited runtime work for a later explicit reload metric | Do not mix reload gains into build/install; no ARM or MDE performance reproduced | Prior art / outside current package-build path |
| P18 | Managed C: prototype 3.303 -> 2.426 s; shared-source/hook fixes independently pass 29 normal/optimized tests and full artifacts | Retain mechanism evidence; investigate a shared-toolchain implementation instead of recommending this private-PDM/FastAPI-specific SDK | Generalizability and maintainer acceptance precede more CI; earlier smokes are not paired performance or Mac proof | **Diagnostic-only; current form rejected for adoption, campaign paused** |
| P19 | Matched C: uv samples show stock/managed roughly 5.85/6.00 s; build/pip roughly 13.37/13.16 s | Reject a runtime-distribution switch as a demonstrated performance fix | Three pairs; no convincing advantage; distributions differ beyond PGO and no causal compiler claim | Runtime branch integrated; no adoption recommendation |
| P20 | One official public-sdist profile: 2.089 s attributed wall; raw deflate 0.246 s (~11.8%), CRC 0.0030 s (~0.14%); recipe differences are not binary acceleration proof | Reject CRC-specific work for this workload; no custom codec/runtime rebuild justified; any deflate lead needs stronger owner-level value evidence | Profile elapsed is not unprofiled CPU/savings; no nested-time addition, compiler causality or Mac ratio claim | [Complete attribution](arm-build/compression-path/attribution/REPORT.md) retained; no implementation |
| P21 | SDK-added safety walk repeats metadata queries; historical ~0.524 s / 10,578 Python calls is not a clean gain measurement | Retain as SDK engineering evidence, not a FastAPI/shared-toolchain optimization recommendation | Do not optimize overhead introduced solely by the rejected bespoke route and call it progress on the original build | [Source note](arm-build/profiles/sdk-validation/README.md) retained; **no implementation planned** |
| P22 | Five C: pairs: baseline median 5.9503 s; suppression 5.9812 s, about 0.52% slower; only 1/5 pairs favored suppression, with overlapping ranges | **Reject and stop** for this workload; do not recommend a flag or upstream default change | All payload/metadata/RECORD checks and Windows semantics matched; both retain five known script-mode failures; no Mac/scan-causality claim | [Local screen](arm-build/shared-toolchain/uv-bytecode/LOCAL-SCREEN.md) retained; no further checks/CI justified |
| P23 | Generic 68-line PDM archive patch; eight focused proofs and owner-config lint/format pass; conservative four capped payloads plus normal overhead | Keep the small owner-level candidate pending real typing and broader compatibility checks; no FastAPI selector or framework | Mypy 2.3.1 download fails TLS; secure OS-store attempt also failed, assistance unavailable. No typing pass or standard-command gain claimed | [Parent review](arm-build/shared-toolchain/pdm-archive-io/MASTER-REVIEW.md): **blocked**, no performance screen or adoption |
| P24 | Pinned uv's temporary build path uses the shared venv constructor that writes activation templates | Retain as a shared-toolchain source lead; do not propose omitting files without cost and compatibility evidence | Existing whole `uv venv` timing is not activation-file attribution; a negligible benefit fails the maintainer gate | [Source triage](arm-build/shared-toolchain/uv-activators/REPORT.md) complete; no implementation, measurement or CI |
| P25 | V2 passed its micro gate; five stock-build pairs changed 5.7688 -> 5.6076 s median (~2.79%), below the 5% advancement gate; four pairs favored it | Park the common-toolchain lead, preserve all V1/V2 evidence and no further tuning | Local overlap/uncertainty, Mac benefit unmeasured, five existing mode failures retained; no CI/adoption | `V2-STAGED-SCREEN.md` retained; no advancement |
| P26 | Existing CI auth/cleanup repeatedly spends much longer around `git submodule foreach`; six setup/removal windows contain 8.103 s paired gap with identical command counts | Collect actual Actions Node/Git/helper provenance and matched read-only command context before any shared-toolchain proposal | Log windows are not exact subprocess durations or emulation/MDE proof; checkout scope stays separate from build-only | [Checkout audit](arm-build/ci-foundation-audit/CHECKOUT-AUDIT.md) and new analysis collectors; no optimization patch |

## Relative benefit and maintenance review

| Proposal family | Likely macOS benefit | Windows-specific case to prove | Maintenance assessment |
|---|---|---|---|
| Fewer imports/processes and log suppression | Shared | Larger Windows startup cost, if measured | Low complexity, but measured log/site changes have insufficient value |
| Selective archive extraction | Shared | Larger protected-Windows cost per newly materialized file/scan | Moderate, fail-closed configuration coverage required; preferred over custom format code |
| Native/custom archive writer | Shared | Material reduction in Windows duplicate opens/stats/scans beyond the simpler extractor | High; do not adopt based only on Q: speed or the old Mac time |
| Dependency ZIP/bytecode cache | Shared | Larger protected-Windows import/scan cost | Extra provisioning/ABI complexity; noisy gain does not justify adoption |
| Avoid redundant staging, rewrites and copies | Shared in principle | Demonstrated Windows scan amplification on C: | Prefer the smallest standard-tool change supported by scan/workload evidence |

Report both `seconds saved` and `R = Windows median / Mac median`. A shared speedup with unchanged or worse R is not parity progress, even if it is independently worthwhile.

The initial C: matrix confirmed that a Q: win is not sufficient: the selective control regressed during **sdist creation**, not extraction, with a different mode-correction adapter. The later same-writer/source follow-up did not reproduce that stall and measured 6.275 s full extraction versus 3.300 s selective extraction. This supports the bounded extraction proposal, not scanner causality. No Defender scan trace was authorized; the native consent dialog timed out. The custom Node writer is not the preferred adoption candidate.

## Competing hypotheses and research tooling

| Hypothesis | Evidence/tool needed | Current assessment / next gate |
|---|---|---|
| Different timed workload | Pin benchmark scripts, exact commands and stage boundaries; inspect raw receipts | The separately supplied prior timing table is not source-matched or comparable to package-build seconds; HOBL exposes several distinct metrics |
| Emulation or wrong architecture | PE machine headers, runtime architecture and native-extension inspection | Python, Node, uv, tar, Git launcher, `_hashlib` and Pydantic core inspected as ARM64; this does not prove every dependency or SIMD path |
| Slower interpreter/toolchain build | CPython release scripts, actual binary provenance/build flags, CPU-bound stage measurements | Published managed Windows ARM PGO verified; Mac artifact reports PGO+LTO. Same-host runtime controls show no convincing advantage; no isolated PGO/LTO causal claim |
| Compiler/project settings | Identify a compiled component on the critical path before inspecting its flags | FastAPI distribution packaging itself is pure Python; CPython/native dependencies may matter in other stages |
| Filesystem/scanning | Matched C:/Q: operations and phase clocks; permitted WPR/Defender attribution | Location effect measured; MDE causality still unproven; no protection changes |
| Slow or source-built dependency | Pinned dependency graph, wheel tags/PE headers, pip/uv install reports and build logs | Audit actual benchmark dependencies first; packaging and installation are different costs |
| Missing ARM acceleration | Native library versions/build recipes plus representative CPU microdiagnostics | ARM64 execution is verified for selected tools, but PGO/SIMD quality remains separate and unproven |
| Scheduling/concurrency | Parent/child CPU and wall time, process-local affinity, appropriate worker sweep | Do not assume 20 cores help serial packaging; prior pip thread changes require original attribution and source verification |

Prior-art source audits are recorded in [PRIOR-WORK.md](PRIOR-WORK.md). None of these hypotheses is accepted solely because previous work or a RICE estimate suggests it.

## Loop and CI readiness

1. Workers return concrete scripts, raw measurements, failed cases and a confidence assessment.
2. Update this table: accept, reject, refine or escalate each proposal with a reason. Do not equate an untested suggestion with an optimization.
3. Apply the ecosystem/portability ranking and maintainer gate first. Integrate only a justified, simple candidate and obtain independent verification; diagnostic prototypes are not adoption candidates.
4. Dispatch a budgeted ARM CI experiment only after that adoption gate and local tests, static checks, bootstrap/build smoke, canonical inputs and full artifact checks pass. Record the runner-only question beforehand.
5. Inspect the resulting medians, ranges, correctness and setup costs. If Windows remains slower, update the table and continue; do not stop at an improvement percentage.

The constraints are owned by [CIRCUMSTANCES.md](CIRCUMSTANCES.md). [arm-build/WORKBOARD.md](arm-build/WORKBOARD.md) owns task state. Raw second-round experiments live under `arm-build\round-2`.

Before spending CI, screen a promising candidate serially and, where useful, with only four CPUs assigned to its **own process tree**. Native psutil affinity queries work on this host. This is a conservative capacity check, not an emulation of GitHub hardware, and must not alter other processes or shared-machine power/security settings.
