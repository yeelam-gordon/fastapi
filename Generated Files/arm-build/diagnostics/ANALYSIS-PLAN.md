# Matched ARM analysis: evidence before optimization

This is an analysis lane, not an official performance-improvement run.
The next CI allocation is gated on local integrated collection and independent
review. Existing comparisons remain exploratory because their inputs/modes
failed strict comparison.

## What existing logs already establish

Windows minus Mac; different rows are nested or different workloads and must
not be added:

| Scope | Windows | Mac | Observed gap | Meaning |
|---|---:|---:|---:|---|
| One isolated complete build, median of seven | 3.1288 s | 0.9504 s | 2.1784 s | Primary build-only gap; internal stages unavailable |
| One dedicated/no-isolation build, median of seven | 2.6787 s | 0.7302 s | 1.9485 s | Most of the observed gap persists; not a timed setup decomposition |
| Checkout step, one coarse observation | 19 s | 3 s | 16 s | Separate CI-job latency, not package build time |
| Six Git credential setup/cleanup intervals (`git submodule foreach`) | 8.5415 s | 0.4381 s | 8.1034 s | Repeated command-family lead, not exact subprocess or CPU time |
| Repository fetch log group | 2.7232 s | 2.0993 s | 0.6240 s | Smaller checkout difference; no evidence to prioritize network tuning |

Both runners emitted 34 selected Git commands. Actual Actions Node
architecture was not recorded. Git launcher architecture does not establish
which shell/helper ran. The old parent import probe did not capture backend
child imports. Source: `ci-foundation-audit\AUDIT.md` and `CHECKOUT-AUDIT.md`.

The local read-only Git probe also distinguishes a costly no-op
`git submodule foreach` from a cheap config query, but that local result is not
a matched Mac result or an explanation of the CI difference.

## First questions for the pipeline

1. Split the real stock build into identified backend-hook windows on both OSes;
   preserve complete-build context and an unassigned remainder.
2. Compare stage wall gaps first. Then use matched hook user/kernel CPU,
   function/import profiles and I/O/memory observations to discriminate causes.
3. Keep checkout/auth separate: capture the actual Actions Node runtime,
   PATH-selected tools and read-only Git command context, including candidate
   helper identities where exposed. Do not assert emulation or MDE causality.
4. Choose the next intervention by differential critical-path seconds, expected
   full-command value, owner and review burden, not by a Windows-local hotspot.

## Enabled separate collection passes

| Data | Actual collection | Limitation that must remain visible |
|---|---|---|
| Complete stock build | Warmup plus three uninjected context builds | Analysis context, not parity proof or a paired optimization experiment |
| Actual isolated hooks | PID/PPID, role, monotonic window and resource snapshots | Bootstrap/export boundaries; no complete native-process-family CPU claim |
| Functions | Per-hook cProfile with self/cumulative times and callers | Elapsed instrumentation, not unprofiled CPU/savings |
| Imports | Importtime on identified actual Python hook children | Early startup outside redirected child logs is unassigned |
| Allocations | Separate tracemalloc peak/allocation pass | Python heap, not native RSS or all process memory |
| Process resources | User/kernel CPU, native memory/I/O where available | Lifetime peaks are not deltas; Windows logical I/O is not Mac block I/O |
| Runtime/runner identity | Source/tool/binary hashes, CPU/RAM/filesystem, codecs, image/run identity | Unknowns/conflicting origins retained, not guessed |
| Checkout context | Actions Node receipt plus readonly Git timings/identities | No-op probe is not authentication timing or proof of helper execution |
| Native traces | Requested capability/privacy-gated native adapter | Currently unavailable without safe owned-process capture/export; explicit gap, never zero |

Native raw traces are excluded from public artifacts. No Defender exclusions,
TLS bypass, UAC change, drive-trust change or global configuration is part of
collection. All profiles are ineligible for performance claims.

## Readiness and interpretation

Resolve the reviewed wheelhouse-manifest, tools/source split and actual
Actions-JSON contract defects, plus shallow-checkout unit-test portability.
Validate a fresh wheelhouse and the actual two-checkout layout locally.
Require all four intended hook roles and each requested portable profile type.
Record failures and missing capabilities rather than producing empty success.

The five stock Windows source-script mode failures remain correctness failures,
not waived differences. Collecting diagnostic data does not establish
artifact-identical parity or any foundational OS/toolchain cause.
After one budgeted analysis allocation, compare like scopes and rank absolute
gaps; request a narrower follow-up only where those results justify it.
