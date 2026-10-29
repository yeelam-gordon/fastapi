# P25: pathlib relative_to — source feasibility only

2026-10-29. **Disposition: credible, bounded upstream source lead; no patch or
adoption recommendation.** GOALS/PERSONA/current
`INVESTIGATION-AND-PROPOSALS.md` read. Shared-toolchain work ranks first;
maintainer value and small review cost remain mandatory. Parity is unmet,
CI capacity limited, and no run is authorized.

## Evidence and decision

| Hypothesis / confidence | Evidence | Unknown | Owner / review cost | Proposed discriminator |
|---|---|---|---|---|
| Ancestor construction is a real source lead — **high** | One existing OFFICIAL PDM 2.5 public `build_sdist` profile: CPython 3.13.15 native ARM Windows, C: NTFS, original FastAPI 79. 2.088757 s wall / 1.796875 s process CPU. `relative_to`: 2,535 calls, 0.2197513 s cumulative, 0.0200833 s self. Nested Sequence membership: 2,535 calls, 0.1409257 s cumulative. [S1–S3] explain repeated parent construction and normalization. | Unprofiled cost, depth distribution and realizable savings. | CPython pathlib; narrow branch rather than changing general Sequence membership. | One semantic proof described below, not timing. |
| A small default/no-walk_up path can avoid ancestor Path allocations — **medium** | For stock classes, same parser + same parsed drive/root + normalized component-prefix equality is the lexical condition; preserve original-case tail for output. Existing parsed/cached fields and `_from_parsed_parts` support this. [S1,S4] | Exact implementation size, Unicode equivalence and net value have not been proved. Broad subclass/duck-type support would increase risk. | CPython; potentially small exact-built-in fast path with unchanged generic fallback, but tests dominate review. | Bound to stock PurePosixPath/PureWindowsPath and concrete stock Path classes; retain fallback for subclasses and walk_up. |
| Supported runtimes already fix these allocations — **high: false at inspected releases** | Current stable **3.15.2** and supported **3.14.10**, both released Oct 25, still enumerate parents through Sequence membership. Pinned main also does so. [S2,S3,S5,R1,R2] | Other runtime improvements or PDM compatibility may still make an upgrade useful; no build timing evidence. | Runtime/toolchain owner; supported upgrade preferable to a private stdlib fork if a relevant fix is later found. | No upgrade-as-this-fix claim. No custom fork. |
| All relative_to time belongs to a stdlib algorithm problem — **high: unsupported** | Existing JSON callers: PDM `_show_add_file` 1,269 calls / 0.1160884 s cumulative; `_collect_files` 1,264 / 0.1034724 s; vendored metadata `_get_files_from_globs` 2 / 0.0001905 s. These sum to the relative_to total, not independent savings. | Whether PDM can reuse a previously computed relative name or avoid redundant logging preparation without changing behavior. | PDM backend versus CPython boundary; callsite reuse may be simpler, but not demonstrated here. | Do not remove logging or replace path semantics speculatively. |
| Generic win means Windows/Mac parity progress — **low** | Avoiding Path allocation could benefit POSIX/macOS too. Windows additionally lowercases each constructed ancestor's string; POSIX does not. [S1] | Common Mac gain, Windows-specific fraction, ratios, artifacts and dependency compatibility. | Shared tools, not FastAPI-specific machinery. | Keep Mac/compatibility gates; no parity or seconds-saved claim. |

Archive opens (~0.457 s), compression (~0.246 s) and CRC (~0.003 s) remain
separate leads. The 0.220/0.141 s numbers are nested elapsed/profile times,
**not additive savings**, CPU attribution, or a full standard-frontend benchmark.
Removing parent iteration cannot remove all relative_to work.

Parent source triage additionally confirms pinned PDM `base.py` L336–341
computes `full_path.relative_to(self.location)` for each member before printing.
The earlier log-suppression trial showed no convincing gain: neither its
~0.131 s cumulative logging frame nor the ~0.220 s relative_to frame promises
unprofiled savings. PDM build/get-requires entrypoints already import builders
lazily; no eager-builder-import change is warranted. These are supplied parent
findings, not newly executed experiments or independently fetched PDM source.

## Semantic envelope a maintainer would need

* Compare **parsed** anchors and component boundaries, never raw string
  `startswith`: `/a` is not `/ab`; `C:foo` is not `C:\foo`; rooted-without-drive
  Windows paths are not drive-absolute paths. Different drives, UNC shares,
  extended Windows anchors, POSIX `/` versus `//`, empty paths and equal paths
  must retain current results/errors. Root ancestor and equal-path cases must
  return the correct tail or `.`. A drive-only `C:` is a valid ancestor of
  `C:foo`, not of `C:\foo`. Existing parser handles alternate separators.
* Use current Windows **lower()**, not Unicode `casefold()` or filesystem
  collation; POSIX remains case-sensitive, including on macOS filesystems that
  happen to be case-insensitive. Unicode expanding lowercase mappings (e.g.
  dotted capital I), contextual casing and composed/decomposed spelling need
  explicit proof against current equality. Never slice original text by the
  length of a normalized string. Return original spelling from parsed tail.
* Parsing removes empty separators and `.` but preserves lexical `..`.
  `a/../b` must not be resolved to `b`; no `abspath`, `resolve`, filesystem
  access, cwd lookup or symlink interpretation belongs in this operation.
* Leave **walk_up=True** on the existing algorithm, including rejection of
  walking through `..` in the base and different-anchor errors. Default-path
  failure must retain ValueError behavior; preserve input coercion, TypeError
  handling and the 3.13 deprecated-extra-argument warning path. 3.14 removed
  those positional extras and now tests `hasattr(other, 'with_segments')`;
  copying its coercion into 3.13 would be an unrelated compatibility change.
* `_from_parsed_parts` calls `_from_parsed_string`, which invokes
  `with_segments`: retain that output factory. Arbitrary subclasses can
  override equality, parents, parser or `with_segments`; eliminating their
  intermediate objects may change behavior. A narrowly guarded built-in path
  plus the old fallback is more credible than claiming equivalence for all
  subclass implementations. Do not optimize `_PathParents.__contains__`
  globally merely to shorten relative_to.

Existing standard tests are inherited from
`test_pathlib_abc.py`: `test_relative_to_common` (L1023),
`test_relative_to_windows` (L1099, including UNC later in that method),
and `test_is_relative_to_common/windows` (L1204/1237). They cover equal/empty,
relative/absolute, drive-relative, case, incompatible anchors and walk_up.
`test_pathlib.py` also checks deprecated extras (L323).
These are source-inspected, **not executed**. Maintainer proof needs both pure
flavours on any host, concrete/subclass factory preservation, explicit Unicode,
root-prefix traps and lexical-dot cases, not a few happy-path examples.

## Existing attribution, not a new invention

Barney Gale's **GH-111429 / PR #111431**, merged 2023-11-12 as
[`d7cef7bc7ea5478abb90a37c8ffb0792cc6e7518`](https://github.com/python/cpython/commit/d7cef7bc7ea5478abb90a37c8ffb0792cc6e7518),
already skips unnecessary `with_segments` coercion and returns pre-parsed
results. **Those improvements are already in the profiled 3.13.15 source**;
they are not a newly discovered 3.14 upgrade fix or an ancestor-membership fix.
PR #113882 / GH-113528, also Barney Gale, merged as
[`cdca0ce0ad47604b7007229415817a7a152f7f9a`](https://github.com/python/cpython/commit/cdca0ce0ad47604b7007229415817a7a152f7f9a),
explicitly distinguishes generalized pathlib ABC implementations from the
battle-tested public PurePath implementation; its temporary-object-free ABC
algorithm is **not evidence that public PurePath was fixed**.
PR #130199's coercion change is
[`d88677ac20b9466387459d5adb2e87b7de64bc19`](https://github.com/python/cpython/commit/d88677ac20b9466387459d5adb2e87b7de64bc19).
Bounded GitHub issue/PR searches found no direct newer ancestor-allocation fix;
this is not an exhaustive claim that no issue exists.

## Maintainer value and exactly one next proof

The case for CPython is a common allocation pattern visible in a real packaging
profile, applicable beyond FastAPI; the case against immediate adoption is one
profile, significant semantic surface, unknown Mac effect and an alternative
PDM callsite owner. A small built-in-only branch with existing generic fallback
is worth **one future authorization-gated, non-timing semantic proof**: in an
isolated CPython source checkout, draft only that branch and run focused
upstream pathlib tests plus the edge cases above, comparing outputs/errors and
subclass factory behavior to the pinned baseline. Reject if equivalence needs
a broad rewrite or special-case framework. No implementation now; no runtime
fork, monkeypatch or FastAPI patch. Only after that proof could separate
authorization consider representative standard-command Windows/Mac measurement
and complete artifact checks. None was run or scheduled here.

## Immutable primary citations

* [S1] [3.13.15 public implementation, parents L30–53, equality L175–204,
  factories/parser L245–275, relative_to L365–404](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/pathlib/_local.py#L365-L404).
* [S2] [3.14.10 release source, parents L49–72, relative_to L476–503](https://github.com/python/cpython/blob/b703b2c5e704341d61e367b9b940b77ed11dded0/Lib/pathlib/__init__.py#L476-L503).
* [S3] [Main snapshot at retrieval, relative_to L479–509](https://github.com/python/cpython/blob/16f209ba7d812e27554ad5c809af0c899341eaa1/Lib/pathlib/__init__.py#L479-L509).
  Direct pinned raw-file inspection, **not an indexed-default-branch result**.
* [S5] [Current stable 3.15.2, relative_to L479–509 and parents L52–75](https://github.com/python/cpython/blob/5e58eaad7c58df58dfa8ea549c87996e01dd1077/Lib/pathlib/__init__.py#L479-L509).
  Its loop accumulates `..` in a list rather than enumerating steps; it still
  constructs ancestor Paths for membership. This is not the proposed fix.
* [S4] [Documented relative_to lexical contract L619–658 and with_segments
  L723–744](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Doc/library/pathlib.rst#L619-L658).
* [T1] [Inherited standard tests](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/test/test_pathlib/test_pathlib_abc.py#L1023-L1203);
  [3.13-specific tests](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/test/test_pathlib/test_pathlib.py#L323-L334).
* [R1] [Official 3.14.10 release announcement](https://www.python.org/downloads/release/python-31410/)
  (release page is mutable; source is pinned by [S2]).
* [R2] [Official 3.15.2 release announcement](https://www.python.org/downloads/release/python-3152/)
  (mutable; source pinned by [S5]). 3.15.0 was released Oct 9 and is superseded;
  3.14 is not the latest stable feature series as of this report.
* Existing local evidence: `..\..\compression-path\attribution\codec-attribution-9a73f3ea23c7\stats.txt`
  and `stats.json`; immutable content hashes in `PROVENANCE.json`.
