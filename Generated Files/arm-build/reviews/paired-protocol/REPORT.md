# Independent paired-protocol review

Reviewed harness commit `73577fc72` on `review/arm-paired-protocol`.
**Disposition: reject readiness pending PP001–PP003 and integrated gates.**
No build, benchmark, CI, push, protection change or producer edit was performed.
Only this review directory is owned by this change.

Read PERSONA, CIRCUMSTANCES, PROPOSAL, INTERFACES, PAIRED, all three protocol
Python files and the manual workflow. Also read wrapper/lock commit
`547d0de41dce2cd18ac7754ed8ddde3f9860f406` through `git show`, without integrating
it. SDK PC001/PC002 fixes at `3c103...` are reported committed by the coordinator;
their independent re-verification is **not** claimed here or counted as harness
defects.

## Consequential findings

### PP001 — caller-isolation evidence is not enforced

**High severity; high confidence.** Locations:
`protocol/measure_pairs.py:750–758`; `protocol/compare_pairs.py:12–50`.

The measurement gate accepts any nonempty wrapper JSON dictionary. It does not
check schema/status/errors, fresh environment identity, unique environment root
across invocations, successful create/install/identity/sdk/cleanup phases,
cleanup completion, matching workers/input hashes, or phase/outer-clock bounds.
The comparator does not require a wrapper receipt at all.

Repro: `repro_review.py::test_missing_or_failed_reused_caller_receipts_still_claim_parity`.
Both missing receipts and identical `{"status":"failed","environment":"reused"}`
receipts across all candidates produce `sdk_caller_isolated_sample_parity: true`.
This is a fixture counterexample, not an actual bad wrapper run.

Expected: reject absent, malformed, failed, reused or identity-inconsistent
lifecycle evidence before accepting caller-isolated measurements. Validate the
committed wrapper's actual schema, including `environment.existed_before`,
`exists_after_cleanup`, identity and all phase results; retain raw reports.
The real wrapper now records the needed lifecycle fields, making a strict gate
possible without inventing another wrapper/reporting framework.

### PP002 — equal missing code identities can produce parity

**Medium severity; high confidence.** Locations:
`protocol/compare_pairs.py:12–23,74–76`.

Cross-OS equality is not completeness: empty `tool_hashes`, empty harness
revision, absent uv executable hash/binary receipt and non-hash runtime strings
all pass. The comparator checks runtime hashes only for truthiness.

Repro: `repro_review.py::test_empty_code_identities_still_claim_parity`.
Both reports have empty code identities and invalid runtime hashes; comparison
returns parity instead of rejecting evidence.

Expected: require the declared versioned input inventory, valid full revision
and digest forms, uv/native-runtime receipts and wrapper-linked identities before
cross-OS equality. This does not claim that normal `code_receipts()` currently
emits an empty inventory; it demonstrates that the advertised fail-closed
postprocessor can accept incomplete report data. No payload normalization is
an acceptable substitute.

### PP003 — polling-only child ownership can accept a leaked process

**Medium severity; high confidence in control-flow defect, medium confidence in
real-run incidence.** Location: `protocol/measure_pairs.py:156–195`.

Descendants are discovered only while the launcher is alive. If it exits before
the first poll, no descendant query occurs, the kill loop is empty and the sample
can succeed with a live owned child. A short-lived intermediate process between
polls presents the same ownership-loss risk. Such a process can escape timeout
cleanup and interfere with later samples.

Repro: `repro_review.py::test_successful_fast_parent_never_checks_or_kills_owned_child`
uses a controlled successful-exit launcher and live owned-child fixture.
`succeeded(result)` is true; descendant enumeration and child termination were
never called. No real process was leaked by this test.

Expected: maintain durable ownership of the invocation's process family across
launcher exit, reject surviving descendants and terminate only that family.
An OS-owned process group/job lifecycle is a concrete alternative to sampling
ancestry; do not broaden cleanup to names or unrelated processes. The wrapper's
own failure cleanup does not establish harness ownership after abrupt exit.

## Bounded positive conclusions

- Fixed source is the full `79cab5bed28b24d92c185d236feb33f5783dfeb3`; canonical
  archive bytes and Git modes are separate from the research HEAD.
- Exactly two manual native-ARM jobs, five fixed B/S1/S3 blocks plus disclosed
  smokes; no replacement samples or automatic retries were found.
- Parent timing brackets the complete wrapper invocation; CPU is unavailable,
  not launcher zero. Goal failure remains distinct from job/infrastructure
  failure. Best correct S1/S3 is independently selected on each OS.
- Only the exact five Windows **B** 0755-to-0644 script differences qualify as a
  known failure; B remains incorrect/ineligible. Unexpected SDK mode/payload/
  metadata/member/RECORD failures stop measurement. Existing tests verify the
  five-script exception and reject a changed mode value.
- RECORD member hashes/sizes/coverage are checked against raw payload bytes
  before canonical row comparison. Ordinary payload/mode hashes are not
  normalized. No waiver for PC001/PC002 was found.
- Windows paths are placed on C: and checked against actual NTFS receipts;
  native runtime/uv binaries are inspected, and native Mac universal2 is allowed.
  Hosted runtime/volume behavior remains unexecuted.
- Raw code/lock/oracle hashes are byte-sensitive. Root attributes do **not**
  cover nested candidate/protocol inputs (`git check-attr` reports unspecified
  for protocol Python and oracle JSON). The reviewed workflow already sets
  `core.autocrlf=false` through `GIT_CONFIG_*` before both checkouts. Thus this is
  not a demonstrated defect in that workflow; direct/default Windows checkouts
  remain fragile. Coordinator's proposed targeted LF attributes should cover
  versioned code/locks/oracle/workflow only, leaving captured reports untouched.
  Verify real checkout identities before runner authorization.
- The fixture-oriented implementation has an understandable need for source,
  subprocess, archive and comparison boundaries. No evidence-backed simpler
  equivalent justifies an additional abstraction/LOC complaint.

## Executed commands and receipts

Working directory: `Q:\fastapi\Generated Files\worktrees\paired-protocol-review`.
Master tool interpreter:
`Q:\fastapi\Generated Files\arm-build\.venv\Scripts\python.exe`.
Paths below are relative to that working directory.

| Invocation | Final result |
|---|---|
| master Python `Generated Files\arm-build\protocol\test_pairs.py` | exit 0; 8 tests |
| master Python `-O Generated Files\arm-build\protocol\test_pairs.py` | exit 0; 8 tests |
| master Python `Generated Files\arm-build\reviews\paired-protocol\repro_review.py` | exit 0; 3 counterexample tests |
| master Python `-O Generated Files\arm-build\reviews\paired-protocol\repro_review.py` | exit 0; same 3 counterexamples |
| master `tools\ruff.exe check --no-cache` on measure/compare/test_pairs and repro_review | exit 0; all checks passed |
| master `tools\actionlint\actionlint.exe -color -shellcheck= -pyflakes= .github\workflows\arm-build-experiment.yml` | exit 0; no diagnostics |

Passing counterexamples establish current undesirable acceptance, not a fix.
Initial `python -m ruff` exited 1 because that environment lacks the module;
used the already-installed standalone Ruff instead, with no install. An initial
review-only E402 diagnostic was corrected before the final clean run.
Actionlint's external shellcheck/pyflakes checks were explicitly disabled.

## Unexecuted integration gates / uncertainty

Wrapper/SDK commits are not integrated in this review worktree. Run their focused
normal/optimized tests and full frozen-source C: smokes only in coordinated
integration; verify offline common backend pins, distinct fresh caller roots,
all phase costs, cleanup/failure propagation and independent archives. Re-run
LF identity checks from actual Windows/Mac checkouts. Only later authorized
native runner jobs can establish allocation/runtime/volume and cross-OS results.
No performance, durability, physical-hardware or MDE-causality conclusion is
supported here. Confidence in hosted behavior and performance is low/unknown.
