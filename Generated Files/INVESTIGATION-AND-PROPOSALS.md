# Optimization loop: Windows ARM must match or beat Mac ARM

**Status: active; the goal is not reached.** Partial speedups are evidence, not completion. Continue investigation, proposals, local proof and independent verification; spend additional fork CI capacity only after the readiness gate passes.

## Acceptance target

Keep the complete FastAPI source-distribution-to-wheel workload and accepted package semantics. The historical Mac reference is 0.730 s median, but the earlier cross-platform comparison was rejected. That number is only an initial screening reference—not a permanently frozen finish line. Evaluate applicable common optimizations on both platforms; compare best validated configurations and report their ratio. A new accepted comparison must use canonical input bytes and preserve all required executable modes.

Local timing is a screening tool, not proof that the hosted runner meets parity. Physical-device parity remains a separate goal.

## Investigation and proposal table

**Current execution priority:** finish the integrated P18 readiness gate before spending more CI capacity. SDK correctness, strict caller receipts, CW002 argv compatibility and actual frozen C: deployment have passed bounded checks. Real preflight then exposed a normal-exit ownership failure and rejection of the official uv version's build metadata; both block the campaign and are under repair. Zero new packaging samples or ARM CI runs have executed. P20 independently researches compression without changing the frozen candidate or adding a dispatch requirement. P13/P14/P19 research is complete. Complex packaging prototypes remain diagnostic evidence, not adoption recommendations. IDs remain stable as evidence changes.

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
| P18 | Managed C: prototype 3.303 -> 2.426 s; portable shared-source/hook fixes independently pass 29 normal/optimized tests and full artifacts | Keep the small candidate gated on fair paired-OS protocol, not only golden artifacts | Earlier caller smokes are not paired performance results; final C: campaign and Mac benefit remain unmeasured | SDK/receipt/argv/deployment gates passed; LOCAL-OWNERSHIP-004 and LOCAL-UV-VERSION-002 block real campaign |
| P19 | Matched C: uv samples show stock/managed roughly 5.85/6.00 s; build/pip roughly 13.37/13.16 s | Reject a runtime-distribution switch as a demonstrated performance fix | Three pairs; no convincing advantage; distributions differ beyond PGO and no causal compiler claim | Runtime branch integrated; no adoption recommendation |
| P20 | Compression/CRC compiler and ARM acceleration have not yet been isolated from filesystem work | Inspect existing profiles and exact distribution/zlib recipes before proposing a later diagnostic | No inference from ARM64/PGO labels alone; distinguish actual binary evidence, Mac benefit and maintenance cost | `compression-path` / primary-source research only; no implementation or readiness blocker |

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
3. Integrate the simplest correct candidate and obtain independent verification. Repeat local experiments when a new finding justifies them.
4. Dispatch a budgeted ARM CI experiment only after local tests, static checks, bootstrap/build smoke, canonical inputs and full artifact checks pass. Record the runner-only question beforehand.
5. Inspect the resulting medians, ranges, correctness and setup costs. If Windows remains slower, update the table and continue; do not stop at an improvement percentage.

The constraints are owned by [CIRCUMSTANCES.md](CIRCUMSTANCES.md). [arm-build/WORKBOARD.md](arm-build/WORKBOARD.md) owns task state. Raw second-round experiments live under `arm-build\round-2`.

Before spending CI, screen a promising candidate serially and, where useful, with only four CPUs assigned to its **own process tree**. Native psutil affinity queries work on this host. This is a conservative capacity check, not an emulation of GitHub hardware, and must not alter other processes or shared-machine power/security settings.
