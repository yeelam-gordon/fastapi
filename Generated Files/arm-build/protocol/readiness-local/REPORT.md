# Local Windows v4 preparation — blocked, no campaign run

The latest authoritative receipt is **`frozen-preflight.json`**. The C: sparse
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
