# Frozen v4 integration review

Reviewed exact master `102ddabcb3a03b33915cb11534925c0951c2df72` in an
immutable, detached sparse clone under this review directory on Q:. Root and
producer worktrees were not edited. Native helper lifecycle experiments were
**not** repeated.

**Verdict: high-confidence bounded pass of the integration gates reviewed;
no new concrete blocker found before the coordinated full local C: campaign.**
This is not a full native packaging pass, CI authorization or parity result.

## PP001 / PP002 / PP003

- **PP001 remains addressed.** Exact schema-v1 phase clocks and command gates
  now agree with wrapper identity `-B -I -c`, SDK `-B -E -s`, and required
  `dont_write_bytecode: true`. All five caller phases, including cleanup,
  must fit inside the wrapper clock, which must fit inside charged command wall.
  The committed wrapper's fixture tests exercise its actual invocation builder.
- **PP002 remains addressed.** Real `code_receipts()` on the sparse clone
  succeeds against the **complete pinned Git tree**, from its nested tool
  directory. The inventory includes `owned_process.py` and its tests; the
  independently checked helper digest equals its raw file bytes. Missing helpers
  cannot fall back to ancestry polling. Existing comparison tests retain
  independent native-OS hash acceptance.
- **PP003 integration concern addressed, high confidence within the helper's
  non-detaching-command contract.** `measure.run()` calls `run_owned()` and
  serializes its complete Receipt. Both controller `succeeded()` and comparator
  reject failed ownership, survivors, incomplete cleanup, errors, timeout,
  nonzero exit and absent command clocks. Independent fixtures update the whole
  result coherently, rather than merely breaking mirrored fields. Helper
  cleanup errors remain in the receipt, and cleanup/handle/pipe failures cannot
  establish success. Native helper correctness relies on the separately reviewed
  lifecycle lane's evidence; it is not newly established by these mocks.

## Static lifecycle / timing review

Windows supervisor joins its dedicated Job before launching the target; the
POSIX supervisor creates a session/group before launching a non-detaching target.
The wrapper no longer calls `start_new_session` or changes `process_group`;
its POSIX phases inherit outer ownership. On interruption it does not kill the
shared controller group. Windows wrapper process-group flags do not provide
breakaway from the enclosing owned Job.

Helper command start is recorded immediately before target spawn. End is after
the target/family drain and ownership cleanup, including wrapper create/install/
SDK/cleanup work. Only pre-command supervisor/ownership setup is separated as
`infrastructure_wall`; post-target cleanup is not shifted there. Raw infrastructure
samples remain in reports and summaries but not variant command ratios. Missing
clocks are unavailable, never zero. Target stdout/stderr are retained separately.
No CPU/scanner attribution is introduced.

## Executed proof and limits

Master interpreter:
`Q:\fastapi\Generated Files\arm-build\.venv\Scripts\python.exe`.
All fixture scratch paths were on Q:. Test suites were invoked from the sparse
clone's `Generated Files\arm-build\protocol`:

| Commands, normal and `-O` | Results |
|---|---|
| `test_pairs.py` | exit 0 each; 15 tests, including actual nested sparse Git inventory |
| `test_isolated_build.py` | exit 0 each; 6 fixture tests including no-detach and bytecode flags |
| own `test_v4_integration.py` | exit 0 each; 4 focused integration tests |
| existing standalone Ruff `check --no-cache` on measure/compare/helper/wrapper and own test | exit 0 |

Logs are the six `v4-*.log` normal/optimized suite receipts beside this report.
The first deeply nested Git fixture exceeded Git's default Windows filename
limit; setting **process-local** `GIT_CONFIG_COUNT=1`,
`GIT_CONFIG_KEY_0=core.longpaths`, `GIT_CONFIG_VALUE_0=true` fixed that test
environment limitation. The initial sparse selection also omitted backend.lock;
adding the committed protocol locks fixed the fixture prerequisite. Neither
required producer changes or changed final test behavior.

Sparse clone preparation used `git clone --shared --no-checkout Q:\fastapi`,
non-cone selection of protocol/candidate Python, protocol/root locks,
oracle JSON, setup CJS, ci_prepare.py, attributes and the manual workflow,
then `git -c core.autocrlf=false checkout --detach` at the exact SHA above.
To rerun `test_v4_integration.py`, recreate that checkout at sibling
`v4-scratch`; the scratch clone is removed after verification.

**Remaining gates:** one coordinated full C: campaign on the frozen integration
must establish actual wrapper commands, lifecycle clocks, fresh environments,
offline locked backend and independent artifact/smoke results for B/S1/S3.
Only subsequently authorized native runner jobs can establish Windows C: NTFS
receipts, actual native Mac runtime and process-group behavior for this complete
chain, cross-OS raw code/lock/oracle identities, fixed schedule completion and
correct artifact comparisons. Five-block results do not prove cross-day
durability or physical-machine parity.

Confidence: **high** in reviewed wiring, fail-closed fixture behavior, inventory
and bytecode command agreement; **medium** in complete native end-to-end readiness
until the C: campaign; **low/unknown** in new native Mac execution and performance.
No CI, push, performance build, security review or protection change was run.
