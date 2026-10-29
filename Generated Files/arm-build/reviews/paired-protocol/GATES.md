# Prepared fixed-behavior gates — verification pending

Historical `REPORT.md` and `repro_review.py` are unchanged. The new
`test_fixed_gates.py` expresses the desired rejection behavior rather than
preserving undesirable acceptance. It is intentionally **red** on reviewed
harness `73577fc72`; no producer correction has been integrated or verified.

Receipt fixtures follow the committed wrapper
`a08208414c28b5bf3525345a65380e8b52538971`, schema version 1. This was read with
`git show`, not from a producer's working tree. Fixture identities are synthetic
valid-format hashes, not claims about actual built artifacts or installed
environments.

Coverage:

- Missing/malformed/failed wrapper reports; unsupported schema; workers/errors.
- Missing/malformed/preexisting/reused caller environments; inconsistent
  prefix/base-prefix/executable/backend/user-site identity.
- Missing/malformed/reordered/failed phases; missing/failed cleanup or cleanup
  for an unrelated root.
- Missing/malformed/nonfinite/negative clocks, overlapping phases, phases after
  wrapper exit, or wrapper time exceeding the outer interval.
- Missing/empty/invalid code/source/runtime/uv identities, wrapper linkage to
  source/code/lock/runtime/uv, and native/translated runtime checks.
- Positive control: valid Windows and Mac reports use **different** Python,
  shared-library and uv hashes and are accepted. Binary hashes are linked
  within each OS, never required to match across OSes.

Identity mutations are applied to **both** reports so cross-OS equality alone
cannot make their rejection tests pass. Reuse is tested across separate S1
invocations, not just between different worker variants.

## Preparation receipts

Working directory:
`Q:\fastapi\Generated Files\worktrees\paired-protocol-review`.
Interpreter: `Q:\fastapi\Generated Files\arm-build\.venv\Scripts\python.exe`.

| Baseline-only command | Result |
|---|---|
| Python `Generated Files\arm-build\reviews\paired-protocol\test_fixed_gates.py` | exit 1; four test methods, 43 failing rejection subcases |
| Same command with `-O` | exit 1; same 43 failures |
| Standalone master `tools\ruff.exe check --no-cache` on the new gate file | exit 0 |
| Historical `repro_review.py` | exit 0; three original counterexamples |

Both positive-platform-hash controls pass. Full baseline diagnostics are
preserved in `fixed-gates-baseline.log` and
`fixed-gates-baseline-optimized.log`. The failures document missing baseline
gates, not test/tooling execution failures. No producer files were edited.

## Later verification

**Await a new committed producer SHA and the separate PP003 lifecycle design
assessment before final verification.** The new gates do not impose an
unreviewed process-group implementation or re-adjudicate PP003.

For a supplied committed protocol checkout, set `PAIR_REVIEW_PROTOCOL` to that
directory, then invoke the gate file with normal and optimized master Python.
Unset it afterward. The tests import the supplied protocol read-only and use
in-memory report fixtures; they never run a child, create an environment or
build a package.

First establish the positive fixture still represents the actual receipt
contract. Any necessary fixture adjustment must be attributed to a documented
schema/design change, not used to remove a failed rejection requirement.
Preserve the historical baseline receipts. No CI or C: smoke/performance work
is authorized by these tests.
