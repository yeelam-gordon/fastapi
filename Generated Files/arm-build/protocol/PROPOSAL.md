# Next ARM CI: bounded acceptance contract

**Decision: prepare, do not dispatch.** One future authorized workflow run, two native ARM jobs, five paired blocks per OS, three variants per block; no automatic retry. This document changes neither source nor harness. A partial Windows improvement is not completion.

## Evidence and question

Read: [persona](../../PERSONA.md), [goals](../../GOALS.md), [circumstances](../../CIRCUMSTANCES.md), [proposal table](../../INVESTIGATION-AND-PROPOSALS.md), [prior ledger](../../PRIOR-WORK.md), [HOBL audit](../prior-work/hobl/AUDIT.md), [frontends](../frontends/REPORT.md), [stdlib operations](../filesystem/stdlib-ops/REPORT.txt), and [toolchain provenance](../toolchain/PROVENANCE.md).

The two previous fork runs do not establish parity: the first failed macOS provisioning; the second completed both jobs but failed strict cross-OS artifact comparison. Local protected-C: isolated frontend medians of 13.421 / 9.672 / 5.961 seconds describe different frontend/installer combinations, not a prefetch experiment. Current build 1.6.1 uses pip `--no-compile` and no ensurepip on the observed path; credited prior bytecode/ensurepip fixes are not candidates here. HOBL `python -m build` including isolation and `uv build` remain distinct metrics; neither is an SDK inner time.

**Runner-only question:** with identical immutable package inputs and matched caller policy, does the portable three-worker SDK improve on its one-worker control on each OS, and can the best correct Windows pipeline match the best correct, applicable Mac pipeline, including the selected isolation cost?

The local normal-attribute SDK prototype changed 3.303 to 2.426 seconds with all 1269/65 artifact members and full modes matching its Mac reference. This is a promising local screen, not proof for the new source or hosted Mac. The roughly 0.037-second additional noattrs gain does not justify another variant. Do not adopt the complex custom Node writer.

## Immutable inputs and readiness: all required before authorization

- Package source: full commit **79cab5bed28b24d92c185d236feb33f5783dfeb3**, FastAPI **0.162.0**, not the research checkout. Read-only inspection of `source-fastapi` confirmed a clean worktree, no tracked `Generated Files`, `pdm.backend`, and release workflow `uv build`. Historical local source `264cbad...` is not silently relabeled as this source.
- CI obtains source through a **separate checkout at that exact ref**, then makes a canonical Git archive and authoritative byte/mode manifest. Research scripts come from their separately pinned integration commit. Never package the growing research tree; do not time checkout/archive preparation. Validate canonical bytes and Git modes identically on both OSes; do not derive executable bits from Windows filesystem permissions.
- Freeze SDK revision and SHA256 of CLI, selector, writer, wrapper, timing harness, validators, constraints and locks. Record exact argv and environment. The intended SDK CLI is `--source --source-manifest --out-dir --workers 1|3`; its existence and semantics must pass local tests before spending CI. No assumed completed implementation.
- Pin native Python 3.13.15 distribution/release, uv 0.13.6 and pdm-backend 2.5.0, plus every tool/transitive wheel with hashes. Log Python executable/library hashes, native runtime and tool architecture, versions, distribution receipts, OS/runner image, CPU/core count, memory and filesystem. Native universal2 Python is acceptable when actually executing ARM, not Rosetta. Published PGO versus PGO+LTO labels are not causal compiler evidence.
- Pass existing focused SDK/selector tests, static checks, bootstrap, all three full-command local smoke builds, and independent artifact verification on the frozen source. Include ordering, bounded reads, failure cleanup/thread joins, selector configuration rejection, safe extraction, metadata regeneration, and mode restoration. SDK wheel inputs must come only from its just-built complete sdist, not the original checkout or cached selection/payloads.
- Locally verify the chosen outer wrapper's fresh-environment behavior, locked offline dependency resolution, subprocess exit propagation and timer boundaries. If it cannot meet the declared isolation policy, **do not substitute an unisolated candidate**. Stop readiness and revise the proposal before dispatch.

## Minimal variants, identical on both OSes

| ID | Command family / isolation | What its comparison establishes |
|---|---|---|
| B | Actual standard `uv build`, pinned Python/backend, complete sdist then wheel-from-sdist, normal default PEP 517 build isolation | Current release-frontend baseline; not a frozen legacy pip baseline |
| S1 | SDK `--workers 1`, normal attributes, caller creates one fresh isolated tool/backend environment for this invocation | SDK control: includes selection, mode restoration and its different orchestration |
| S3 | Exactly S1, only `--workers 3` differs | S1 versus S3 isolates prefetch's effect within this SDK |

Use the same fresh caller wrapper for S1/S3 on both OSes. A verified `uv run --isolated` wrapper is legitimate **only with the entire wrapper invocation inside the outer timer**; verify rather than infer freshness from the flag. It must not discover project configuration or reuse an installed backend environment between samples. If necessary, implement the wrapper using an explicitly new owned venv plus locked installation, with all creation/install/cleanup charged. Resolve exact supported flags during readiness, not during CI.

One fresh SDK environment shared by its sdist and wheel steps is **caller isolation**, not the standard frontend's two backend environments. Report this explicitly; B versus S3 is an end-to-end packaging-method comparison, **not solely a prefetch gain or identical PEP 517 isolation lifecycle**. Preserve separate metrics:

1. `standard_uv_isolated_wall`: B, spawn through frontend exit.
2. `sdk_caller_isolated_wall`: S1/S3, before wrapper spawn through exit, including environment preparation and cleanup.
3. Optional `sdk_inner_wall`: imports through package completion inside the ready environment, clearly diagnostic and never substituted for metric 2.
4. `provision_wall`: runner Python/tool acquisition, archive preparation and wheelhouse population, separately measured and itemized. Also report provision plus all charged command costs for this run; do not present it as a cold single-build latency.

No extra legacy frontend cell in this budget: retain existing `python -m build` evidence under its own name, without claiming a matched hosted result. Current FastAPI release already uses uv; switching legacy pip to uv is not a new SDK innovation.

## Fixed schedule, caches and measurements

Use **five** blocks on each OS with variant orders **B,S1,S3; S3,S1,B; S1,B,S3; S3,B,S1; B,S3,S1**. This nearly balances ordinal placement and reverses the causal pair. Cross-OS blocks are logical pairs, not simultaneous identical machines. No tuning worker count or sample count after seeing results.

Allow one disclosed untimed preparation/smoke per variant, then five clean samples each. Dedicated tool/download caches are warm, offline and not purged; OS page/security caches are uncontrolled. Fresh child processes, isolation environments, scratch paths and output directories per sample. No source movement during timing, no selection/metadata cache. Keep all Windows timed source/runtime/dependencies/cache/scratch/output on ordinary C: NTFS, not local Q: or Dev Drive; verify and record the actual CI volume. Do not change trust or protection. Keep unrelated disk-heavy work off the measured runner.

Start a monotonic wall timer before spawning the complete command and stop after its exit. Include imports, fresh metadata, full source reads, compression, selection, 64-file extraction where applicable, wheel construction and charged cleanup. Exclude only the declared shared preparation and post-exit correctness verifier. Capture unfiltered logs and failures outside the timed child. Set a predeclared 20-minute job limit and 120-second sample limit; timeout/failure stops that job without replacement. Retain all completed samples and mark the comparison incomplete.

Record all raw walls, medians, min/max, within-OS block deltas S1 minus S3, and Windows/Mac median ratios by variant. Process-tree aggregate CPU is **unavailable** unless collected reliably; launcher near-zero CPU is not zero workload CPU. No profiler in measured children, no MDE/ETW trace without approval, and no scanner-causality conclusion from wall time, C:/Q: differences or unchanged Python open counts.

## Correctness is a separate report, never a performance flag

Produce a per-OS, per-variant, per-sample correctness matrix with independent fields for source identity, sdist/wheel membership, payload hashes, complete modes, metadata and RECORD validation, installed-wheel smoke, and explicit differences. Do not emit a blanket “all equivalent” flag.

An independent oracle derived from canonical source/Git modes and reviewed package selection defines expected members/content; retain a mode-correct reference for this exact source and independently check it. Re-establish counts on 79cab: the old 1269/65 counts are expectations to verify, not permission to force a match. Compare complete tar modes and uid/gid/uname/gname/size, full ZIP permission fields, metadata, RECORD coverage/hash/size and cross-OS payloads. Validate each RECORD against its own wheel; compare canonical RECORD content while documenting only harmless row-order differences. Archive timestamp/compression byte equality is not required; no payload or executable-mode normalization is allowed.

Known Windows B behavior loses execute bits on five sdist scripts. If reproduced, show **B: mode correctness FAIL**, with timing retained as a descriptive control. It does not invalidate S1/S3's independent proof and does not excuse a candidate mismatch. An incorrect baseline is ineligible as a “best correct” winner; an incorrect candidate is rejected even if faster. Never silently fix B's artifacts after timing or waive the five modes.

## Decisions and claims

| Outcome | Decision / permitted claim |
|---|---|
| Source/tool/architecture mismatch, missing sample, or either candidate correctness failure | Incomplete/reject; preserve diagnostics; no parity claim and no auto-rerun |
| S3 improves S1 on Windows but Mac improves similarly or more | Local mechanism may be useful; report absolute savings and ratio change, not Windows parity progress by itself |
| Best correct Windows remains slower than best correct Mac | Goal unmet; update ranked proposals, not the finish line |
| Correct, scope-compatible Windows median <= best correct Mac median | **Sample parity** for this declared warmed workload only; publish ranges and overlap, not durable superiority |
| Small/reversed deltas or broad ranges | Inconclusive mechanism/repeatability; no selective sample removal or extra unbudgeted trials |

For the SDK caller-isolated workload, select the lower validated S1/S3 median **on each OS**, and disclose selection among two predeclared choices. Also show every per-variant ratio so an asymmetric winner cannot conceal shared gains. Include B in the best-correct comparison only if its correctness and isolation contract qualify. Do not compare Windows S3 against an obsolete, slower Mac configuration.

Five blocks can establish observed sample parity, not durability across runner images, days or physical hardware. Durable acceptance needs a later **explicitly budgeted**, unchanged-protocol run on another allocation/day with correct artifacts and the same direction; it is not an unlimited retry requirement or authority to schedule now. Physical approximately-20-core Windows versus approximately-16-core Mac remains separate.

**Scope clarification:** none is needed to prepare or run this bounded comparison when authorized. Before adopting SDK results as the final isolated-build goal, explicitly decide whether caller isolation is acceptable or standard per-hook frontend isolation is required. If the latter, SDK caller-isolated parity is only a subsidiary result; integrate and validate that lifecycle before claiming the goal. Do not silently relax isolation to cross the finish line.

## Cost, uncertainty and recommendation

- **High confidence:** immutable-source and separate-metric requirements; baseline mode failure must remain visible; isolated legacy versus unisolated SDK cannot identify prefetch savings.
- **Medium confidence:** three-worker prefetch merits one controlled hosted screen. The small private PDM 2.5 writer hook and fail-closed selector impose medium coupling/maintenance risk; prefer a supported upstream hook if adoption becomes worthwhile.
- **Low confidence / unknown:** hosted Mac gains, durable Windows parity, scanner causality and compiler/ISA explanations. No additional security changes, system tracing or custom interpreter work is justified here.

Keep the SDK a proposal until its local readiness gates pass and both OS results justify its maintenance cost. This report authorizes no CI, benchmark execution, push or source changes; no schema or implementation is needed for this decision.
