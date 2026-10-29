# Local Windows v4 preparation — prepared, campaign awaiting approval

## Latest authorized preparation: a44aae95

Frozen candidate **a44aae9537e6c9b3a0826d9c55e0ff6db3449379** was fetched from
the local `Q:\fastapi` repository into the existing sparse C: clone. No network
fetch or producer patch was used. The independent evidence attempt is:

`attempts\a44aae9537e6-7e7e580f71dd41a3a6b85213f4d45693`.

Its **`preflight.json`** and the unmodified, actual controller **`prepare.json`**
are the latest preparation receipts. The actual command was
`measure_pairs.py --prepare --uv <owned uv.exe> --source-checkout <read-only source-fastapi> --output <new owned C: controller-output>`.
Full argv, cwd, exit status, environment and preparation clocks are retained.
The controller itself reports **prepared** at the exact frozen revision:
22 tool inputs, 3,233 canonical source files and 26 hashed wheels. Source hashes
match the original canonical archive/manifest. Native runtime/binary identities
and actual C: NTFS volume receipts are retained.

Both controller dependency commands succeeded using only existing verified
offline wheels: `UV_OFFLINE=1`, `UV_NO_INDEX=1`, `UV_FIND_LINKS=<owned wheelhouse>`,
`PIP_NO_INDEX=1` and `PIP_FIND_LINKS=<owned wheelhouse>`. No TLS failure, download,
index fallback or new runtime acquisition occurred. Raw `prepare-0.log` and
`prepare-1.log` are retained. The controller's preparation wall is
10.541253899999 seconds; fixture gates plus preparation took 67.6584427000016
seconds. These are preparation costs, not packaging sample latency or original
cold provisioning.

Normal and optimized gates completed against the frozen C: inputs:

| Suite | Tests per mode | Result |
|---|---:|---|
| Paired controller | 17 | 16 initially pass; opt-in uv test initially skipped |
| Owned process | 14 | Pass |
| Isolated wrapper | 6 | Pass |
| Candidate | 8 | Pass |
| Source reuse fixtures | 5 | Pass |

The initially skipped opt-in test required `PAIRED_TEST_UV`. Without rerunning
any failed test or suite, that previously **unexecuted** real-binary test was
then run explicitly with the owned uv path in both modes: both passed.
`verified-uv-gate.json` and its normal/optimized logs retain the supplement.
The full actual output
`uv 0.13.6 (329bf9448 2026-10-26 aarch64-pc-windows-msvc)` was neither shortened
nor replaced. The preparation-only orchestrator now sets that opt-in path
for future independently authorized attempts.

All original failure receipts below remain unchanged and retain their original
identities. This is a new, authorized candidate preparation, not a replacement
sample. **Zero full FastAPI campaign builds or warmups ran.** Tiny demo builds
inside the focused reuse tests are fixtures, not campaign samples.

The prepared controller output remains at:

`C:\fastapi-arm-build-lab\paired-v4-2a73e36a\f87c928ba5ad409087d1695f0995067e\attempts\a44aae9537e6-7e7e580f71dd41a3a6b85213f4d45693\controller-output`.

Await the independent semantic review and explicit root **GO** before the full
unchanged 18-build controller schedule. There is no readiness approval, Mac
result, ratio, CI dispatch, replacement sample or automatic retry.
Root subsequently reported a bounded positive independent helper review, but
requires the pending **PC002** cleanup-only repair and its review before GO:
an initial handle-close failure must not skip remaining handles or mask the
original termination error. This lane has not patched or exercised that repair;
the successful preparation above retains the original a44aae95 identity.

## Historical blocked snapshot: 102ddabc

The historical authoritative receipt is **`frozen-preflight.json`**. The C: sparse
checkout was locally fetched from `Q:\fastapi` and updated to root's exact frozen
commit **102ddabcb3a03b33915cb11534925c0951c2df72**, without changing this evidence
branch. Its actual `code_receipts()` now passes inventory discovery: all 22
receipt inputs match their frozen Git blobs. Frozen paired tests pass (15).

**LOCAL-OWNERSHIP-004 blocks execution:** the frozen C: ownership suite ran once
and failed `test_normal_unfiltered_logs_and_separate_infrastructure`. The actual
receipt reports exit 0, no timeout, established ownership, `survivors=True`,
cleanup complete and no errors. Command wall is 0.36868049999975483 seconds;
infrastructure is 0.1746759000016027 seconds. This is a helper fixture, not a
packaging sample. The raw failure is retained in
`frozen-normal-test_owned_process.py.log`; its exact command is in the JSON.
No retry or replacement was performed. The cause is not established.
The gate sequence stopped; remaining frozen test modes were not executed.
The exact uv version-string blocker below also remains in this frozen commit.
Root has not sent campaign GO.

The earlier `prepared-state.json` records preparation against the old tools;
raw CLI and test logs are beside it. `preparation.json` preserves the first
preparation attempt, which
stopped at an import-order lint error in this lane's own orchestrator. That
error was corrected, lint passed, and preparation continued without repeating
builds, samples, or fixture tests. No producer files were changed.

## Prepared inputs

- Owned disposable root:
  `C:\fastapi-arm-build-lab\paired-v4-2a73e36a\f87c928ba5ad409087d1695f0995067e`.
- Source: clean read-only `source-fastapi` at
  `79cab5bed28b24d92c185d236feb33f5783dfeb3`; canonical archive and 3,233-file
  manifest prepared once. The manifest is retained here; archive and extracted
  source are on C:. Archive SHA256:
  `d10f4af3101343ddcd332a7873c06759b858ea944bbc9c317dd938580f15ee9e`.
- Harness: `1052c15b1f22cf4e2db043f04de0000bb8139532`, separate from package
  source. The C: checkout has independent Git metadata, workflow non-cone sparse
  patterns, no object alternates, 25 materialized tracked files, and verified
  exact Git blob bytes and Git modes. Historical research is not materialized.
- Private native managed CPython 3.13.15 environment, copied native uv 0.13.6,
  26 copied offline wheels, owned scratch/cache/output directories, unchanged
  protection. Runtime executable/library and uv binary hashes, wheel hashes,
  actual C: NTFS volume receipts and whitelisted environment are retained.
- Hashed tooling and smoke locks installed offline into the private preparation
  environment. No mutated shared environment was reused. No new runtime was
  installed or downloaded.
- Actual controller/wrapper/SDK and uv build CLI help retained. Pair (13),
  ownership (11), wrapper (6), and candidate (8) tests pass under normal and
  optimized Python. Tests ran against Q: code; no C: package benchmark ran.

## Explicit execution gates

1. **LOCAL-INVENTORY-001 (resolved by frozen update):** known `tool_inventory()` subtree-relative
   `git ls-tree` inventory bug. Root reported producer repair `d5536b`; this
   lane initially did not refresh or locally patch it. The later frozen update
   passed the actual inventory gate.
2. **CW002 (producer repair integrated):** root-confirmed caller argv validation
   rejected the actual wrapper `-B` flags. The frozen commit includes the
   repair and its paired fixtures pass.
3. **LOCAL-UV-VERSION-002:** actual `uv.exe --version` returns
   `uv 0.13.6 (329bf9448 2026-10-26 aarch64-pc-windows-msvc)`.
   Current `measure_pairs.py` compares that complete string to exactly
   `uv 0.13.6`; the verified correct binary therefore fails that preflight.
   `uv-version.log` is the direct non-build reproduction. Do not mask the
   version output or change producer code locally.

Await resolution of the two remaining observed blockers and root's explicit
**go**. The frozen C: update and new tool identities are retained separately;
old preparation identities have not been relabeled as the repaired harness.

Use the actual unchanged v4 controller, including its per-sample source copies
prepared outside the command timer. All copies and timed inputs remain on C:.
Run its disclosed B/S1/S3 warmups and five fixed blocks only once, with the
120-second sample and 20-minute job limits, no replacements or automatic retry.
Retain full command/ownership clocks, separate setup infrastructure, wrapper
cleanup, oracle/RECORD checks, installed-wheel smoke, and all raw artifacts.
The five known baseline script mode failures remain correctness failures.

## What this evidence does not establish

Zero packaging builds, warmups or timed samples ran. There is no campaign
lifecycle proof, artifact oracle result, installed-wheel smoke result, performance
claim, Mac receipt, or cross-OS ratio. Test durations are not build measurements.
Process-tree aggregate CPU is unavailable, not launcher CPU zero. Native hosted
Mac, paired comparison, authorized CI, durability and hardware gates remain.

`prepare.py` is a preparation-only entry point: all input paths are explicit,
each invocation creates a unique disposable child and unique evidence attempt,
and it never calls the producer's measurement path. It does not repair producer
inputs or authorize execution.
