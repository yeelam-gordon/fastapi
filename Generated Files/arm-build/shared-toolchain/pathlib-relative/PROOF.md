# P25 authorized semantic prototype — 2026-10-29

**Go for parent source review only; no performance screen or adoption authorized.**
Production change: **13 added / 0 removed lines**, solely inside CPython
`Lib\pathlib\_local.py`. Five focused regression methods add **62 test lines**.
`pathlib-relative.patch` is the complete upstream-shaped patch; `production.patch`
is the production-only subset. Ignored `cpython\` is pinned to
`4061bc4c35f7c26f25264666d4ba083b93d2f6f9` (3.13.15), not committed.

## What the branch does

After existing coercion/warnings, only exact stock PurePosixPath,
PureWindowsPath, PosixPath or WindowsPath objects with identical parsers are
eligible. Each operand is checked with `any(type(operand) is cls for cls in
stock_types)`: class equality is never used. `walk_up` and
deprecated-extra-argument calls are excluded.
It formats **one candidate ancestor string from parsed drive, root and tail**,
using the same formatter and `or '.'` as Path stringification. Windows lowers
that **entire formatted string**, then compares with the base's existing
`_str_normcase`. Only equality returns through the existing
`_from_parsed_parts` factory, slicing the original tail to preserve spelling.
There is no raw string-prefix test or per-component normalization.

This mirrors the string the old algorithm would construct for the ancestor at
that tail depth, without allocating that ancestor Path or enumerating nearer
ancestors. All misses, mixed parsers, subclasses and walk_up calls continue
through the original loop. This does not change `is_relative_to`, the parser,
Sequence membership, public APIs or input coercion. Building the stock-types tuple, identity-check generators and
formatting/checking an unsuccessful candidate adds work to some
fallback calls; net performance is **unknown**.

Baseline actually returns `.` for `C:Σ` relative to `C:ς`, and `Leaf` for
`C:Σ/Leaf` relative to `C:ς`. `C:/Σ/Leaf` instead matches base `c:/σ`
and rejects `c:/ς`. Drive-relative casing context is therefore material.
Both baseline and candidate return `Leaf` for `C:/İ/Leaf` relative to
`c:/i` + combining dot. Lowered text lengths never determine output slicing.

## Proof actually executed

Existing **CPython 3.13.15 native ARM64** interpreter, fresh processes,
`-I -S -B`, with source `Lib` prepended **before pathlib is imported**.
The runner asserts no existing pathlib module and checks `_local.__file__`
against the ignored source checkout. No installed module is swapped out.
TEMP/TMP and cwd are confined to ignored `cpython\proof-work` on Q: before test
imports; `-B` prevents bytecode writes. Only source/test files in this owned
checkout are changed. Unittest's incidental elapsed-time footer is retained
in raw logs but is **not a benchmark or performance result**.

| Run | Tests | Passed | Skipped | Failures / errors |
|---|---:|---:|---:|---:|
| Pristine upstream source/tests (`baseline.log`) | 407 | 342 | 65 | 0 / 0 |
| Pristine production + new parity tests (`baseline-expanded.log`) | 447 | 376 | 71 | 0 / 0 |
| Candidate production + same new tests (`candidate.log`) | 447 | 376 | 71 | 0 / 0 |

Both expanded runs have identical skips: 30 require POSIX flavour on
Windows-flavour test instances, 28 require Windows flavour on POSIX-flavour
instances, and 13 require a POSIX-compatible concrete host. PurePosixPath and
PureWindowsPath suites both execute on Windows; concrete POSIX remains skipped.
Individual test IDs/reasons and loaded source-module hashes are recorded in
`baseline-expanded-modules.json` and `candidate-modules.json`.

The runner selects complete PurePath, PurePosixPath, PureWindowsPath and
PurePathSubclass upstream suites, plus relative_to/is_relative_to/with_segments
methods from Path, WindowsPath, PosixPath and PathSubclass suites. Existing cases
exercise UNC/anchors, drives, walk_up, coercion, warnings and factory state.
New tests add Unicode whole-string casing, lexical dot/dotdot, root/component
boundaries, observable subclass factory fallback and equality-overloading
metaclass exclusion on **both operands**. New tests pass on baseline
because this prototype intentionally changes allocation strategy, not results.

## PATH-001 correction after parent review

The original `type(operand) in stock_types` guard was **not exact-class safe**:
tuple membership can invoke the subclass metaclass's equality. Parent supplied
a confirmed semantic counterexample. This is a genuine violation of the
promised fallback boundary, not an excluded pathological input.

Two regressions use an equality-overloading metaclass. One subclass makes
instance equality false and requires baseline ValueError; the other retains
normal equality but makes `parents` raise LookupError, proving fallback without
non-reflexive instance equality. Both tests check subclass `self` and subclass
`other`. Their base uses the actual class produced by the upstream suite's
class factory, so PurePath/Path factory cases test the correct subtype relation.

`path001-before-production.patch` preserves the previously reviewed 12-line
version from commit `ecac7b24dedcb3ac25b2754ca7543d4ea910b7a2`.
With the final test file, that old version runs 447 tests and has **10 failures,
0 errors, 71 skips** (`path001-before.log`). Untouched production and the
identity-fixed 13-line version both pass as above. The new guard uses
transparent `is` checks only; it has no id, name or module-name workaround.

## Exact commands and provenance

From this evidence directory, setup was:

```powershell
git clone --quiet --filter=blob:none --no-checkout --depth 1 --branch v3.13.15 https://github.com/python/cpython.git cpython
git -C cpython sparse-checkout set Lib/pathlib Lib/test/test_pathlib Lib/test/support
git -C cpython checkout --quiet
```

Git sparse-pattern arguments are repository-relative Git paths, not Windows
filesystem operands. Cone mode also fetches necessary root stdlib/test support.
No interpreter/compiler build or package installation was performed.

Expanded proof commands (fixed candidate present initially):

```powershell
git -C cpython apply --reverse '..\production.patch'
git -C cpython apply '..\path001-before-production.patch'
python -I -S -B semantic_proof.py path001-before *> path001-before.log
git -C cpython apply --reverse '..\path001-before-production.patch'
python -I -S -B semantic_proof.py baseline-expanded *> baseline-expanded.log
git -C cpython apply '..\production.patch'
python -I -S -B semantic_proof.py candidate *> candidate.log
git -C cpython diff --numstat
git -C cpython diff --check
git -C cpython apply --reverse --check '..\pathlib-relative.patch'
```

The first pristine run used `python -I -S -B semantic_proof.py` before patching
either source or tests, redirected to `baseline.log`. The final runner adds
hash/skip manifests; its hash, patch hashes, base/candidate source and test
hashes, logs and manifest hashes are in `SEMANTIC-PROVENANCE.json`.

## Confidence, attribution and remaining gates

* **High:** selected baseline/candidate tests agree, including verified sigma
  and dotted-I cases; source origin and exact line count are recorded.
* **Medium:** small owner-level strategy is reviewable and semantically credible,
  not exhaustive equivalence for every possible Unicode/path input.
* **Low / unmeasured:** speedup, fallback overhead, Mac benefit, build artifact
  equivalence, PDM compatibility on newer runtimes and Windows/Mac parity.

Barney Gale's existing python/cpython#111431 optimization remains credited in
REPORT.md and unchanged in the patch; python/cpython#113882 concerns the ABC
boundary, not this new prototype. No existing ancestor-allocation fix was found
in the inspected supported releases or pinned main.

Stop here for parent review of the 13-line production change. No further proof
or standard-command performance run is authorized by this result. No production,
installed-runtime, FastAPI, global-config, CI, C-drive, push/PR/owner-contact
or dependency changes were made. Full CPython suite, native macOS/concrete POSIX
and end-to-end packaging remain unexecuted.
