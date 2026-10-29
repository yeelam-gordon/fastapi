# Current SDK validation: localized C: diagnostic, not an adoption result

## Result and decision

**Medium confidence: propose one local scandir-walk differential experiment.**
The current recursive safety walk is material (about half a second here).
Reject the claim that wrapper SDK 3.125s minus older prototype 2.426s proves
0.7s validation overhead: those are unpaired, different-context measurements.
Do not change production code, timers, filtering, or trust boundaries on this evidence.

| Observation | Wall seconds | Process CPU seconds |
|---|---:|---:|
| One fresh-process, unprofiled SDK build call, workers=3 | 3.006188 | 2.359375 |
| Separate fresh-process cProfile build call, workers=3 | 3.129159 | 3.015625 |
| Separate actual preflight-prefix diagnostic | 0.586047 | 0.531250 |
| Safety walk within that prefix | 0.524441 | 0.500000 |
| Configuration within that prefix | 0.006241 | 0.000000 |

These are build-call clocks, **not interpreter-startup-inclusive wrapper phase
clocks**. CPU is `time.process_time()` for the process, including its reader
threads; clock granularity explains a zero for short configuration work.
The prefix diagnostic has lightweight counting/timing wrappers, not cProfile.
It executes the current build function's actual AST prefix through manifest
comparison, stopping immediately before its `ops` import. It is not a second
clean full-build sample or a production replacement.

## Attribution

`profile.json` retains cumulative function top 40, call counts and selected
attribution rows; `diagnostic.pstats` stays untracked on C:. Selected inclusive
cProfile times (overlapping, **do not sum**):

* `source_files`: 0.600516s; recursive `source_files_nested`: 0.593258s.
* `checked_children`: 0.258839s; all-context `Path.stat`: 12,224 calls / 0.517304s.
* All-context `Path.is_file`: 4,799 calls / 0.213776s; `Path.is_dir`:
  3,673 / 0.142123s; `Path.lstat`: 3,672 / 0.170332s.
* `Path.resolve`: two calls / 0.000638s. Resolution is not the large term.
* `safe_path`: 4,516 calls / 0.028685s; configuration (preflight and archive):
  two calls / 0.020772s. Manifest/configuration work is not the dominant term.
* Buffered sdist `build_artifact`: 1.120932s; gzip `write`: 1.024347s;
  tar `gettarinfo`: 1,268 calls / 0.645985s.
* Archive selector: 0.198438s; selected extraction with attributes:
  0.174690s; wheel `build_artifact`: 0.402597s.

The separate preflight diagnostic counts **10,578 Python `os.stat` calls in
the safety walk**, versus 10,594 across the entire prefix. `Path.lstat` delegates
to `os.stat(follow_symlinks=False)`, explaining zero direct `os.lstat` calls.
Current code first lstat-checks every entry for links/reparse points, then
calls `is_dir`, then (for regular files) `is_file`, repeating metadata requests.
It scans all 3,233 canonical files, not just the 1,268 sdist payload files:
the extra paths are intentionally necessary for unexpected-file/hook rejection.
This is high-confidence duplicate **Python metadata-call** attribution, not a
count of kernel operations or evidence of MDE causality.

cProfile was enabled only in the calling thread: reader-thread work is not
reliably attributed. Thread/join/queue entries in the raw top 40 do not establish
reader CPU or disk-read costs. Profiling overhead, warm state, and the single
sample prohibit a speedup estimate from subtracting these runs.

## Small next proposal (not implemented)

Replace only the recursive source enumeration with an `os.scandir` walk that
obtains one `DirEntry.stat(follow_symlinks=False)` per entry and classifies its
cached mode. Reject symlink mode and **any reparse attribute before descent**;
do not use a following-link classification. Retain every unexpected regular
path for the same exact manifest-set comparison.

Keep unchanged: root/output resolution and separation, exact PDM 2.5 guard,
manifest safe paths/modes/backend-state ownership, cleanup environment guard,
case-insensitive local-hook rejection, all configuration restrictions, archive
selection, payload reads, PDM metadata regeneration, and extraction attributes.
Root `.pdm-build` must still have its exact spelling, be a directory, contain
only the same permitted regular children, and have the exact decoded sentinel;
reject junctions, unknown children, malformed state, and aliases before PDM runs.
No cached payload/metadata, skip-validation flag, trusted-source flag, narrower
walk, or timing-boundary relocation.

Before any production change, differential-test acceptance/rejection against
the original on canonical and reused-state trees plus extra files, nested/root
links and junctions, mixed-case hooks/state, bad sentinels, nonregular nodes,
canonical state ownership, disabled cleanup, invalid manifest modes/paths and
unsupported config. Then pair whole-build runs and require the unchanged strict
oracle. No local alternative was implemented in this bounded lane, so guard
equivalence and net savings of that proposal remain **low confidence/unproven**.

## Reproducibility and boundaries

* Branch: `investigate/arm-sdk-validation-cost`; no producer edits, CI, push,
  global installs, or helper/source-code mutation.
* Current candidate CLI/contracts and `protocol\wrapper-evidence\readiness-v2\S3.json`
  were read before execution. Current `build.py` SHA-256 begins `421ef1a8`,
  unlike historical S3's `8bf1d280`; evidence uses current branch code.
* Execution code/input/temp/output is under
  `C:\fastapi-arm-build-lab\sdk-profile-2a73e36a`.
  Reused managed native ARM64 3.13.15 / PDM 2.5 environment is located
  by retained runtime-comparison `results.json`; no install was required.
  `-E -s` and owned C: temp paths were used. **Isolation deviation:** `-E`
  ignored `PYTHONDONTWRITEBYTECODE=1`; backend imports generated shared
  environment `.pyc` files at 00:03:43. No dependency/source edits or installs
  occurred, but the environment was not strictly read-only. These samples do
  not satisfy that requested isolation condition. Shared caches were not
  deleted/restored. Committed harnesses now set `sys.dont_write_bytecode=True`
  before further imports; future commands should additionally use `-B`.
  Measured executable-script hashes identify the original C: copies, not this
  post-measurement bytecode-hardening edit. No second clean sample was run.
* Canonical archive was copied once from the retained caller-readiness export,
  not exported from the research tree. TAR Git comment confirms revision
  `79cab5bed28b24d92c185d236feb33f5783dfeb3`; every source payload hash matches
  the retained canonical Git-mode manifest. See `input-verification.json`.
* `clean.json` / `profile.json` record ABI, current code/input hashes,
  process clocks and artifact hashes; `identities.json` adds executable,
  harness and strict gold inventory hashes.
* Both builds passed the existing strict Mac gold inventory comparison:
  1,269 sdist and 65 wheel members, payloads, full modes and independent
  RECORD coverage/hash/size checks, all **outside** build clocks.
  The profile build reuses the recognized `.pdm-build` state from the clean run;
  normal backend cleanup remains inside its build call.
* Existing candidate/reuse guard tests passed (13 tests) using copied C: code.
  No new walk means no new production behavior to validate.
* Raw profiles, copied code, archives, environments and full build logs remain
  outside Git. Only scripts and human-readable receipts are committed here.

**High:** current artifact correctness and duplicate metadata-query structure.
**Medium:** local safety-walk materiality warrants a narrowly scoped experiment.
**Low:** prospective scandir net savings or guard equivalence until tested.
Isolation acceptance is not claimed because of the recorded bytecode deviation.
No CI-readiness delay, Mac performance, or adoption claim.

## Source-only follow-up: retain DirEntry metadata, future loop only

Reviewed 2026-10-29 against this branch's unchanged
`candidate\build.py` (`checked_children`, `source_files`,
`source_files_nested`) and Python **3.13.15** sources below. This follow-up
changes documentation only: no prototype, benchmark, C: writes, candidate edits,
CI request, new acceptance blocker, or change to the current matched experiment.
Other readiness work must not wait for this proposal.

### Mechanism and platform assessment

Python 3.13 `Path.iterdir()` **already uses `os.scandir`**, but retains only
`entry.path` and constructs Paths, discarding DirEntry's metadata cache [2].
The opportunity is retaining that information, not introducing scandir into a
listdir-based implementation. Current `checked_children` then calls `lstat`;
`is_dir` and, for files, `is_file` each call `stat` again [3].

A possible replacement would use a context-managed scandir per directory,
obtain `entry.stat(follow_symlinks=False)` once, and use that single result for
link/reparse rejection and `S_ISDIR` / `S_ISREG` classification. Do not classify
via a default-following call or convert back to Path and repeat type queries.
Keep entry metadata local to that invocation; close directory iterators on
success and failure, preferably before descending to avoid depth-many open
handles. No ordering guarantee is added; no result survives into another build.

On Windows, the 3.13 docs say a non-following DirEntry stat can use enumeration
data, including for reparse entries; following a reparse point can require a
separate query [1]. This makes the proposed cache reuse especially plausible
there. On macOS/Unix, the first DirEntry stat still requires a metadata query;
reusing its result can nevertheless eliminate the current repeated queries.
This safety walk needs full mode information, so a cheap directory-type hint
alone is insufficient even when `d_type` is available. There is no measured
Windows/Mac ratio here. PEP 471's historical os.walk speedups are **not SDK
predictions**, and its general stat example is not this workload [4].

### Non-negotiable behavior and unresolved error semantics

* Reject `S_ISLNK(mode)` **or any** `st_file_attributes & 0x400` before descent,
  even for broken links, junctions and non-symlink reparse tags. An
  `is_symlink`-only or `is_junction`-only replacement is weaker. Preserve the
  existing non-Windows missing-attribute fallback; demonstrate Windows mode
  and attribute equivalence, not identity of the entire stat result. DirEntry's
  Windows inode/device/link-count fields are documented as zero [1].
* Enumerate the same entire tree, including dotfiles, unselected source and
  unexpected paths; only the **root** recognized `.pdm-build` state is excluded
  from the canonical file list. Nested state-named directories are ordinary
  inputs. Empty directories remain allowed, not new manifest entries. Preserve
  exact relative spelling and POSIX manifest names without casefolding all names.
* Keep root resolution/output separation unchanged: current root `resolve()`
  can follow a root alias; descendant link rejection is not a new root ban.
  Preserve the exact state spelling, flat permitted regular children, decoded
  `*\n` sentinel, canonical state-ownership ban and cleanup-environment guard.
  Sentinel/config/payload bytes are still read each build, and PDM still cleans
  its state inside the build. Retain the current hook-case/configuration rules,
  manifest mode/path checks and exact file-set comparison before PDM loading.
* Propagate enumeration, stat, permission and sentinel-read errors; never
  catch-and-continue or treat an unreadable directory as empty. Do not copy
  PEP 471's illustrative error-skipping example. Prefer explicit stat
  classification over `DirEntry.is_*`, which can suppress `FileNotFoundError`.
  Existing initial `Path.lstat` errors propagate; later pathlib predicates
  suppress only certain errors [3]. Failure timing/exception differences need
  explicit differential tests, not an assertion of automatic equivalence.
* **Open issue:** cached Windows enumeration attributes are not a fresh lstat.
  A disappearance, changed permissions or replaced entry may be observed
  differently, including an error the old explicit query would have raised.
  Neither current code nor this proposal is race-proof; concurrent source
  mutation remains unsupported. That limitation alone does not prove identical
  observable errors. If preserving the fresh lstat probe is required, retain it
  and reuse its result for classification instead; that simpler existing-walk
  change may make a DirEntry-cache rewrite unnecessary. Do not silently relax
  error behavior to obtain the Windows caching benefit.

### Hypothesis ledger and required future tests

| Hypothesis | Current evidence | Unknown | Future acceptance / rejection |
|---|---|---|---|
| SDK safety enumeration has avoidable metadata queries | Exact source repeats lstat/type queries; prior diagnostic ~0.524s / 10,578 Python calls | Clean-isolation effect size; kernel query count | Treat old sample as attribution only; no subtraction-based savings claim |
| Retaining DirEntry data helps Windows most, and can help Mac | 3.13 platform/cache contract [1]; pathlib discards entries [2] | Net SDK gain on either OS, attribute/error parity | Only a later authorized, matched whole-build comparison could establish gain |
| All current rejection guards can survive | Narrow classification-only design above | Cached-stat error differences and platform fixtures | Differential accepted path sets and rejected inputs; no missing guard or swallowed error |
| Complexity is justified | Standard public API; no new dependency | Maintenance versus actual net gain | Reject rewrite if error parity needs fragile special cases, guards weaken, or gain is negligible; consider reusing current lstat result first |

Required tests for any later implementation: canonical tree and reused valid
state; extra/unselected/dot/nested files and empty directories; exact casing,
Unicode names and current hook aliases; root/nested file and directory symlinks,
broken links, Windows junctions and other reparse attributes; nonregular POSIX
nodes; malformed/aliased/linked state and bad/missing sentinel; manifest
extra/missing paths, invalid modes, claimed backend state, disabled cleanup and
unsupported config. Test enumeration/stat/read permission and injected I/O
failures, disappearing entries, iterator closure and no traversal of rejected
targets. Separate real Windows/Mac fixtures from injected stat-result tests;
unsupported fixtures are not a passing platform check. Build rejection must
still precede output creation/PDM hook loading. Finally require unchanged
strict full-mode/payload/RECORD artifacts and current-byte rebuilding after
source/config edits; no cached project metadata or payload is permitted.
These are conditions for that **future change**, not today's readiness gate.

This overhead is **SDK-added preflight safety work**, not an original FastAPI
or PDM build defect. PDM discovery/metadata generation, TAR member metadata,
compression, extraction and wheel creation remain separate work and are not
optimized by this proposal. The old 3.125s/2.426s contexts and the prior shared
bytecode-cache deviation remain unsuitable adoption evidence.

**High confidence:** repeated source-level queries, cache/platform API contract,
and which guards must stay. **Medium:** a small metadata-reuse change is worth
considering later, Windows especially. **Low:** net gain and full cached-walk
error equivalence. **Decision:** retain as a future-loop proposal; reject
production adoption now, and reject the rewrite outright if safety/maintenance
cost exceeds an independently demonstrated benefit.

Primary references inspected (2026-10-29):

1. [Python 3.13 os.scandir / DirEntry](https://docs.python.org/3.13/library/os.html#os.scandir),
   especially `stat`, caching, reparse points, `is_*` errors and iterator closure.
2. [CPython v3.13.15 pathlib _local.py](https://github.com/python/cpython/blob/v3.13.15/Lib/pathlib/_local.py),
   `Path.iterdir` and `Path.stat`.
3. [CPython v3.13.15 pathlib _abc.py](https://github.com/python/cpython/blob/v3.13.15/Lib/pathlib/_abc.py),
   `PathBase.lstat`, `is_dir`, `is_file`.
4. [PEP 471](https://peps.python.org/pep-0471/), rationale, caching and exception
   handling; historical examples do not override the 3.13 contract.
