# Independent PP001 / PP002 correction verification

Producer commit: `8a58b8c68ec184a0146164d86509573355937987`.
Attributed cherry-pick in this review worktree:
`b1fe5b8756326536aa06270b3bc7d5fa05d418c6`.
Producer files were not hand-edited. Historical report, counterexamples and
baseline red receipts remain unchanged.

## Separate dispositions

**PP001: CLOSED for the reviewed receipt-validation contract; high confidence.**
The measurement and comparison paths both invoke the schema-v1 lifecycle gate.
Independent prepared negative gates reject absent/malformed/failed receipts,
errors, reused/preexisting/unclean caller roots, inconsistent environment
identity, missing/reordered/failed phases, wrong cleanup targets and invalid,
overlapping or uncharged clocks. Wrapper source/tool/backend identities and
raw artifact receipt linkage are checked.

The positive gate also replayed **unmodified** committed S1, S3 and S3-after-B
wrapper receipts from `a08208414c28b5bf3525345a65380e8b52538971`; all accepted.
Raw Git blob digests are recorded in the replay logs. Actual phase commands and
outer times come from that commit's `readiness-v2/summary.json`, not new builds.
The source remains `79cab5bed28b24d92c185d236feb33f5783dfeb3`.

**PP002: CLOSED for complete declared inventory/digest/native-receipt validation;
high confidence.** Every required inventory member is independently tested
missing and with empty, nonhex, short and long digests; both OS reports are
mutated identically to avoid accidental rejection by cross-OS inequality.
The real inventory function rejects a Git-tree fixture missing its required
wrapper. Source/runtime/uv/code receipt rejection tests all pass.
The positive control accepts **distinct valid** Windows versus Mac Python,
library and uv hashes, linked within each OS; no binary-hash equality is imposed
between platforms.

**PP003: OPEN.** Polling ownership is unchanged in this producer commit.
Receipt correctness does not prove process containment. Await the lifecycle
lane's approved, implemented owned child-job/group helper and its separate
verification; this review neither implements nor waives that gate.

## Only justified positive-fixture adjustments

1. New inventory validation requires a complete committed tool tree. This
   isolated review checkout has no integrated wrapper files, just the requested
   correction. Its first fixture invocation therefore stopped during setup.
   The former positive fixture's `code_receipts()` disk read was replaced with
   synthetic valid-format hashes over the declared inventory, and **only the
   Git tree read** is mocked to supply that inventory. The inventory, digest,
   native and lifecycle validation functions are real and unmocked.
2. The new artifact-linkage gate requires the independent correctness receipt's
   raw archive digest mapping. The positive fixture now supplies its consistent
   synthetic mapping.

No negative mutation or expected rejection was removed or relaxed. A real
committed-receipt replay was added to ensure synthetic positive coverage is not
the only schema compatibility evidence. It validates captured receipt shape
and linkage; it does not re-open archives or re-certify historical builds.

## Commands / persistent receipts

Working directory:
`Q:\fastapi\Generated Files\worktrees\paired-protocol-review`.
Master interpreter:
`Q:\fastapi\Generated Files\arm-build\.venv\Scripts\python.exe`.
Review scripts/logs are under `Generated Files\arm-build\reviews\paired-protocol`.

| Command | Result / receipt |
|---|---|
| Python `test_fixed_gates.py` | exit 0; 5 methods including inventory subcases; `fixed-gates-8a58.log` |
| Python `-O test_fixed_gates.py` | exit 0; same gates; `fixed-gates-8a58-optimized.log` |
| Python `replay_actual_receipts.py` | exit 0; 3 unchanged actual receipts; `actual-receipt-replay-8a58.log` |
| Python `-O replay_actual_receipts.py` | exit 0; same receipts; `actual-receipt-replay-8a58-optimized.log` |
| Python `Generated Files\arm-build\protocol\test_pairs.py` | exit 0; 12 tests; `producer-tests-8a58.log` |
| Same producer tests with `-O` | exit 0; 12 tests; `producer-tests-8a58-optimized.log` |
| Existing standalone Ruff `check --no-cache` on measure/compare/test_pairs and both new review scripts | exit 0; all checks passed |
| `git diff --check` | exit 0 |

No install, CI dispatch, benchmark or C: build was run. Git reads for immutable
receipt replay are the only subprocesses launched by that replay script.

## Limits

This is bounded validation of committed parser/gating behavior, not an
integrated experiment readiness pass. The positive Git tree is a fixture;
the actual merged wrapper/SDK/harness inventory, LF checkout policy, raw hashes
and full command chain still require coordinated integration verification.
Native Mac behavior is represented by fixtures, not a new Mac execution.
PP003, authorized two-job allocation, C: native smokes, independent new artifact
verification and any parity/performance claim remain outside this result.
