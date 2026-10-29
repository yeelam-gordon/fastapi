# PC001 fix verification

## Revision and disposition

Producer commit `6aba234a2d733b235dc63c3ae10c56611aad83b7` was cherry-picked
into this review worktree as `c3d0a4ff898acee745af2c12d3401d0b018db320`,
preserving producer authorship and its Copilot trailer. No producer files
were hand-edited. This follow-up owns only this evidence and updated
`verify.py` assertions.

**PC001 is closed for the reproduced cleanup failures. High confidence.**
The original `REPORT.md` remains unchanged as historical evidence. Its
pre-fix counterexamples and exact executable expectations are retained in
review commit `f4b3143fc9dca5a4cc9c7193295a0d7abca8eee4`; the two updated
proofs now require the corrected outcomes rather than the old bugs.

- Failed job setup retains the original exception, and a failed handle close
  is added as an exception note and serialized into Receipt.errors. Both
  messages are visible; ownership/cleanup remain false; target never spawns.
- Failed stdin and stdout closes are both recorded, stderr close is still
  attempted, and the job is closed. `run_owned` returns a Receipt preserving
  original invocation error and returncode 7, with cleanup_complete false
  and succeeded false. No remaining pipe is skipped.

The bounded correction adds local exception handling, not a framework.
The checked diff does not alter process ownership or timer boundaries.

## Executed proof

Native Windows ARM64 Python, same review worktree and interpreter as the
original review. All four commands exited zero:

| Suite | Mode | Result |
|---|---|---|
| `protocol\test_owned_process.py` | normal | 11 passed, 4.368s |
| same | `-O` | 11 passed, 4.514s |
| `reviews\process-containment\verify.py` | normal | 5 passed, 1.147s |
| same | `-O` | 5 passed, 1.176s |

The producer suite includes the original nine cases plus both cleanup
regressions. Independent proofs cover both corrected failure cases,
missing executable, both platform timer branches through mocks, and
**real Windows parent death**. The latter again kills only its known
controller and checks/cleans explicitly recorded supervisor, target,
and grandchild PIDs. Unique local helper directories were removed.
`git diff --check` passed. No dependencies, builds, benchmarks, CI, or pushes.

Updated supervisor SHA256:
`9db21a2aab063a424b135588324835947f3d69a2e0d96ab422783d6b4bef9666`.
Future CI must hash/freeze its actual then-current helper bytes; the original
review's supervisor hash is historical, not valid for this revision.

## Remaining critical gates

No new critical finding from this bounded fix verification. This still does
not certify integrated PP003 closure. Preserve the existing gates:

- Producer/harness receipt persistence and abort-before-next-sample behavior,
  plus the known POSIX wrapper group-inheritance prerequisite, are other-lane
  integration work, not new findings here.
- Real hosted Windows inherited/nested-job compatibility remains unexecuted.
- POSIX evidence remains source inspection and unit mocks; confidence is
  medium for those contracts, low for unexecuted macOS runtime behavior.
  Windows parent-death proof is **not** macOS parent-death proof. The
  documented POSIX design does not promise controlling-parent-crash cleanup.

High confidence in exercised local Windows cleanup/ownership/timer behavior
and closure of PC001; no cross-OS certification is claimed.
