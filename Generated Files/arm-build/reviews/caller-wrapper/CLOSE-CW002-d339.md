# CW002 closure on frozen committed inputs

**CW002 CLOSED for strict argv/bytecode receipt compatibility; high confidence.**
Frozen master: `102ddabcb3a03b33915cb11534925c0951c2df72`, including producer
`d339ef2205b79dafe48c72660ba2a03fb3a1e229` and wrapper fix `63b173...`.
CW001 remains closed. The original incompatibility counterexample and all
earlier evidence remain unchanged and apply to their earlier revisions only.

## Independent execution

`verify_frozen_gate.py` stages exact committed Git blob bytes into a unique
owned Q: scratch child, imports those modules, and deletes the child afterward.
The source revision and each staged blob SHA256 are printed in both final logs.
No producer files are edited. A prerequisite cherry-pick encountered a test
conflict and was aborted completely; exact frozen staging was used instead.

Both Windows and Darwin **fixtures** establish:

- Exact identity `-B -I -c` and SDK `-B -E -s` argv are accepted.
- Old/missing `-B` is rejected separately for identity and SDK.
- Wrong `-b` is rejected separately for identity and SDK.
- Missing effective `dont_write_bytecode` and explicit `false` are rejected.
- Effective `true` is accepted with the exact current commands.

These are real validator calls, not mocks of acceptance. The independent
mutation method accompanies, rather than replaces, the producer's new
bytecode-policy regression method. The former CW002 failure conditions now
reject only the intentionally stale/wrong receipts, not current valid receipts.

All existing `ComparisonTests` ran, including the PP001 lifecycle mutations:
missing/failed/reused receipts, preexisting or unclean roots, errors, failed or
missing phases, wrong workers/source/hash, invalid wrapper/phase clocks, bad
backend identity and artifact mapping. PP002 inventory/runtime digest checks
and failed owned-family receipt rejection also pass. No lifecycle gate was
removed or mocked to obtain a bytecode-policy pass; only the existing fixture's
Git inventory discovery is mocked in its comparison tests.

The six frozen wrapper tests also pass, retaining original subprocess error/raw
log evidence, appended cleanup failure, fresh roots, hash/offline argv,
exclusive reports, invalid inputs and bounded POSIX direct-child semantics.
No actual process-family ownership test is claimed from those mocks.

## Persistent results

Master interpreter remains
`Q:\fastapi\Generated Files\arm-build\.venv\Scripts\python.exe`.
From this worktree, all scripts are in this review directory:

| Command | Result |
|---|---|
| `-B verify_frozen_gate.py` | 16 methods PASS; `closure-frozen-normal.log` |
| `-B -O verify_frozen_gate.py` | 16 PASS; `closure-frozen-optimized.log` |
| `-B test_review_guards.py -v` | 8 PASS; `closure-own-normal.log` |
| Same own tests with `-O` | 8 PASS; `closure-own-optimized.log` |
| `-B probe_fixed.py`, normal and optimized | both actual child flags true; no tiny-module `.pyc` or `__pycache__`; `closure-real-probe*.json` |
| Existing master Ruff `check --no-cache verify_frozen_gate.py` | PASS; `closure-ruff.log` |
| `git diff --check` | PASS |

The 16-method suite comprises six wrapper methods, nine comparison methods and
one independent mutation method. The separate eight-method suite overlaps the
six wrapper methods; do not describe these as 24 unique tests. Real tiny-module
probes use the already attributed wrapper fix, not a package build.

The first staging attempt omitted wrapper hash inputs (`backend.lock` and
`candidate/build.py`) and caused two fixture failures before the intended
mocked phases. Its logs are preserved as `closure-initial-stage-*.log`.
Adding those exact committed blobs, without altering producer code or tests,
made both final runs pass. This was incomplete review staging, not a new
producer defect.

## Remaining actual full-build gate

This closes bounded caller receipt/flag compatibility, not integrated build
readiness. The frozen whole command chain still needs an authorized real
caller build with actual fresh creation, locked offline install, native
identity/bytecode receipt, SDK execution, owned cleanup, successful outer
ownership/drain and independent complete artifact validation. Existing older
build receipts are not relabeled as executing these fixes. No C: package build,
matrix, Mac execution, CI, push, scanner or performance claim was made here.
All review validation costs remain separate from any baseline sample wall.
