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
