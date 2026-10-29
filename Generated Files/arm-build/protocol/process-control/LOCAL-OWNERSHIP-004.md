# LOCAL-OWNERSHIP-004: first bounded investigation, unresolved

**Disposition: keep the campaign blocked. No production fix is justified yet.**
Confidence is high in the original recorded failure and the new passing
observations, **low in the root cause**. Passing diagnostics are not replacement
samples, do not invalidate the frozen failed gate, and do not authorize a retry
or campaign.

Read the root's original `frozen-preflight.json` and
`frozen-normal-test_owned_process.py.log` in the local-paired-readiness worktree,
read-only. Their observed successful root plus `survivors=true` is retained,
not rewritten. No file in that worktree or C: runtime/campaign tree was changed.
Production helper and tests remain exactly at `6aba234a2`.

## Executed on the supplied interpreter

`C:\fastapi-arm-build-lab\paired-v4-2a73e36a\f87c928ba5ad409087d1695f0995067e\env\Scripts\python.exe`

Observed CPython 3.13.15 ARM64; `sys.base_prefix` is
`C:\Users\yeelam\AppData\Roaming\uv\python\cpython-3.13-windows-aarch64-none`.
All new files/scratch/logs were under this Q: helper lane.

| Bounded check | Result |
| --- | --- |
| Original normal test alone, unchanged helper | passed, exit 0 |
| 16 trivial normal children with job-only conditional diagnostic | all accepted, no positive accounting observation |
| 16 exact existing `--helper normal` children with same diagnostic | all accepted, no positive accounting observation |
| Existing complete ownership tests, `-B` | 11 passed, exit 0 |
| Existing complete ownership tests, `-B -O` | 11 passed, exit 0 |

These are tiny lifecycle proofs, not performance trials. The 16 exact-helper
records are in `managed-liveness-before.json`; the earlier trivial-child
batch was visible in tool output only. Full final normal/optimized logs are
retained separately. No package builds, heavy workloads, CI, push, source
mutations, or machine changes.

`diagnose_liveness.py` instruments only the existing helper's `_Job.alive`
return. If accounting reports an owned survivor, it immediately queries that
job's documented process-ID list and obtains synchronization-only handles to
record each listed PID's wait state. It records the known supervisor PID.
It does not inspect process names, command lines, environment, or unrelated
processes, and does not add a sleep or grace period before the first check.
The exact normal helper writes only its already-defined owned PID receipt.
All owned scratch directories were removed. None of the 32 diagnostic
invocations entered the positive-accounting branch.

## What this does and does not establish

The full gates continue to reject and clean genuine fast-root/grandchild
survivors and timeouts with this managed interpreter. Normal exit, failure
status and PC001 injected cleanup tests also pass. No production behavior
was changed, so parent-death semantics were not modified; the independent
real parent-death proof was **not rerun** in this investigation. macOS remains
unexecuted.

Accounting that briefly outlives a waited supervisor, interpreter-launcher
teardown, and an actual additional live owned process remain hypotheses.
The original receipt contains no job membership/wait-state evidence to
distinguish them; the new checks did not reproduce its positive observation.
Do not silently reclassify the failed receipt as harmless teardown.

**Minimal next step for root adjudication:** if another focused reproduction
is explicitly budgeted, instrument the original first-positive observation
with owned job member IDs, known supervisor identity and public process wait
states, preserving the original decision. Only evidence that distinguishes
an already-terminated owned process from a genuinely executing descendant
can support a narrow liveness correction. No arbitrary sleep, broad scan,
survivor waiver, or acceptance retry is proposed.
