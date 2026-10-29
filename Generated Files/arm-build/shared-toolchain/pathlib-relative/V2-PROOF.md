# P25 v2: complete stock default path — semantic review only

2026-10-29. **Ready for parent source review, not timing or adoption.**
Production diff against pinned CPython 3.13.15: **18 added / 0 removed lines**.
`V2-PRODUCTION.patch` is the small owner-module diff.
`V2-PATHLIB.patch` adds the complete test diff: 113 lines, including 62 retained
v1 regression lines and **51 new lines in three test methods**.

## Critical assessment and bounded decision

V1 was rejected, correctly: success-only speculative work penalized equal
paths and was repeated by the generic algorithm on misses. Its 210 timings
and thresholds are unchanged, not pooled with anything new. The authorized
v2 decomposition is source-simple because, for **identical exact stock classes
and literal `walk_up=False` only**, the baseline either finds the base as
self/ancestor or immediately raises its first-iteration not-in-subpath
ValueError. It never needs a different-anchor special case on that default
failure path. Thus a direct negative result needs one identical message, not
a new error framework. No broad special cases were necessary.

That argument does **not** extend to mixed classes, arbitrary subclasses,
nonliteral flags or walk_up. All remain on the old algorithm. This is a
distinct complete-default-path design, not reordered class probes, adjusted
timing cases or relaxed thresholds. Its maintainer value remains conditional:
less duplicate work is source reasoning, **not evidence of a speedup**.

## Exact source behavior

* Existing coercion and deprecated-extra-argument warning code is untouched.
  Extra arguments remain on the generic path after the existing warning.
* Guard uses `walk_up is False`, `type(other) is cls`, and explicit stock class
  identity alternatives: no generators, class-equality membership, id/name
  tricks or truth-testing of custom flag objects. Same parser but different
  concrete/pure classes still use generic fallback.
* Equal tail depths compare existing full `_str_normcase` values. Unequal
  shorter base depth uses the reviewed parsed drive/root/tail formatter,
  `or '.'`, and Windows **whole-string lower()**. It does not lowercase
  separate components or use a raw string-prefix test. A longer base fails.
* Success uses the existing `_from_parsed_parts` factory and original-spelling
  tail. Failure raises the exact baseline
  `f"{str(self)!r} is not in the subpath of {str(other)!r}"`.
  The original loop remains verbatim for ineligible calls.
* The baseline does not evaluate a custom walk_up flag when a positive
  relationship is found. V2 preserves that property. In particular a raising
  flag returns a successful relative path without raising; a negative
  relationship evaluates it only in the old fallback.

Reviewed v2 production source SHA-256:
`b6616ee0240d1ced9e2ff3f02dcfbbe0f30e7c5d8b751e6f9f986cce4f4a1e3e`.
Pinned base is `4061bc4c35f7c26f25264666d4ba083b93d2f6f9`,
base `_local.py` SHA-256
`0530b4186ec5845e000bedf5817ff1ac970b9a39a6891ba6789a1776abdea42b`.

## Executed semantic proof

Same existing `semantic_proof.py`, unchanged bytes and selected upstream suites,
run in fresh native ARM64 3.13.15 source-prefix children with `-I -S -B`.
Origin assertion, Q: test cwd/TEMP/TMP, no installed module substitution.
Unittest's incidental elapsed-time footer is retained, not used as a performance
measurement; **no v2 timing screen was executed**.

| Production source | Selected tests | Passed | Skipped | Failures/errors |
|---|---:|---:|---:|---:|
| Untouched pinned baseline + full v2 tests | 471 | 397 | 74 | 0 / 0 |
| V2 + identical full v2 tests | 471 | 397 | 74 | 0 / 0 |

Both runs have identical skip reasons: 30 require POSIX-flavour test instances,
28 require Windows-flavour instances, 16 require a concrete POSIX host.
PureWindowsPath and PurePosixPath both execute on Windows; concrete POSIX does
not. All PATH-001 metaclass/equality/parents and prior Unicode/factory/boundary
regressions remain in the suite.

Three new test methods verify:

1. Raising/side-effect flags are not evaluated on success; a negative case
   raises LookupError for the raising flag, raises ValueError after one false
   evaluation, or walks up after one true evaluation. These expectations were
   verified against untouched baseline, not inferred.
2. Exact default ValueError text for unrelated, longer-base, relative/rooted,
   and component-prefix mismatch cases.
3. Both directions of native concrete/pure mixed classes preserve successful
   output, exact result factory type and incompatible-anchor failure via the
   generic algorithm. Windows runs WindowsPath/PureWindowsPath; the test uses
   native POSIX equivalents when run there.

Commands from the owned evidence directory:

```powershell
git -C cpython apply --reverse '..\V2-PRODUCTION.patch'
python -I -S -B semantic_proof.py v2-baseline *> v2-baseline.log
git -C cpython apply '..\V2-PRODUCTION.patch'
python -I -S -B semantic_proof.py v2-candidate *> v2-candidate.log
git -C cpython diff --numstat
git -C cpython diff --check
git -C cpython apply --reverse --check '..\V2-PATHLIB.patch'
```

`V2-PROVENANCE.json` records base/candidate source/test hashes, exact commands,
patch/log/runner/module-manifest hashes. Individual skips and loaded source
hashes are in the separate `v2-*-modules.json` files.

## V1 preservation and confidence

All **22** previously committed v1 artifacts are archived byte-for-byte under
`v1\`, including source patches, scripts, proofs, PATH-001 results and all 210
microtimings/gates. `V1-ARCHIVE.json` maps their hashes to v1 commit
`a45074ea04a3cb01877474f7ba1b56dcd048c66c`. Root originals are also unchanged.
These are archival artifacts, not a second runnable checkout; ignored
`cpython\` currently contains v2. V1 rejection and Phase B nonauthorization
remain in force.

**High:** selected baseline/v2 semantic parity, flag evaluation and PATH-001
regressions pass, exact source counts and artifact hashes.
**Medium:** source equivalence argument beyond those tests; full CPython suite
and native POSIX/macOS remain unexecuted.
**Low/unmeasured:** v2 performance, actual fallback workload mix, full-build
gain, native Mac benefit or parity.

Barney Gale's existing python/cpython#111431 improvements are unchanged and
remain credited in the v1 source report; this prototype does not claim them.
Stop for parent review of the 18-line diff. No timing, C: writes, runtime
installation, dependency/framework, compiler build, FastAPI/global changes,
CI/push/PR, owner contact, delegation or further design revision was performed.
