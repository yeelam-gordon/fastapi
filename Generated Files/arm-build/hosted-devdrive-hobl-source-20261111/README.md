# Stock HOBL hosted storage replay (source only)

`stock-hobl-storage-ci82-v1` is prospective, not admitted or measured. It is
independent of the blocked local two-runtime SOURCE28 proposal. No existing B
results are replayed or relabeled. No workflow, action, helper, local storage
configuration, grant, source approval, runtime readiness, or budget is changed.

## Source closure

Four physical source copies: `execution.py`, `matched_audit.py`, `controlled_ci.py`,
and `matched.py`. Other libraries/data remain a SHA-bound external source closure,
not duplicated. `SOURCEPINS.json` lists successor and reference SHA256s.
`source_closure.py` adds the explicitly selected reference folder to Python's
module search path; it does not replace modules, classes, or methods.

Set `HOBL_SOURCE_ROOT` to the reviewed `pipe-matched-ci-readiness` folder, keeping
its `hobl-complete-ci` sibling. The reference folder name and relative layout
must match the manifest; its absolute parent may move. On this machine the
default is the source worktree named in the implementation request. Hosted jobs
must set this variable explicitly (including macOS). Both source folders and
the successor belong under the action's selected workspace **before the initial
source seal**. Any later source edit requires a fresh seal and review.

## Consumer API (parent integration only)

Use the existing storage action's default-deny preparation contract separately.
Choose a new absolute `OUTPUT` under its selected evidence/data root. Before any
bootstrap, place the tools, source checkout, and managed/base Python under the
chosen workspace/runtime roots and export the action-rooted `TEMP`, `TMP`,
`TMPDIR`, `UV_CACHE_DIR`, `PIP_CACHE_DIR`, and, for managed Python,
`UV_PYTHON_INSTALL_DIR`. Do not reuse a predecessor venv, cache, source payload,
or seal. The action parent owns those bindings and the fresh initial seal.

For **each independent job**, set:

```
HOBL_SOURCE_ROOT=<selected workspace>/pipe-matched-ci-readiness
MATCHED_PROFILE=stock-hobl-storage-ci82-v1
```

After an authorized parent readiness gate (none is supplied here):

```
<base-python> -B <successor>/controlled_ci.py prepare --profile stock-hobl-storage-ci82-v1 --source <fresh-source-checkout> --output <OUTPUT> --uv <uv> --workers <4-Windows-or-3-macOS> --seconds <actual-remaining-allocation>
<OUTPUT>/venv/<Scripts/python.exe-or-bin/python> -B <successor>/controlled_ci.py run --profile stock-hobl-storage-ci82-v1 --source <same-source-checkout> --output <same-OUTPUT> --uv <same-uv> --workers <same-workers> --seconds <actual-remaining-allocation>
```

These are API descriptions, not authorization to execute. The entry point
requires fork/attempt checks plus a new successor-local `PARENT-REVIEW.json`
with `approved: true`, exact `profile`, SHA256 of this `SOURCEPINS.json`, and
the retained `cli_identity_qualified` prerequisite. No review receipt is issued.
Reference-profile approval cannot authorize this successor.

Preparation reuses common82 once: one venv/compiler per job, not two runtimes
or an SDK manager. `OUTPUT` owns `venv`, `wheels`, bootstrap source, four fresh
`source-01-A` through `source-04-A` trees, and four `payload-*-A` evidence folders.
Measured build/test TEMP is each `payload-*-A/temp`; measured UV cache is
`OUTPUT/uv-cache`; pytest scratch and coverage/artifacts are payload-owned.
Bootstrap pip cache/TEMP inherit the explicitly action-rooted environment.
`OUTPUT` must not exist before `prepare`; its parent must exist. Parent-selected
source/runtime/cache/TEMP/evidence placement therefore covers **full HOBL**,
not just build caches. Upload OUTPUT plus the sealed successor/reference source
and action preparation receipts. Storage preparation/verification and placement
evidence remain the parent's responsibility.

## Semantics and boundaries

Public schedule extensions are keyword-only `schedule`, default ABBA, in
`execution.prepare`, `execution.orchestrate`, `execution.worker`, and
`matched_audit.final`. `execution.sequence(args)` selects AAAA only for the
named profile. CLI workload/audits must go through `controlled_ci.py`.
The original default profile still runs ABBA.

All four rows are A. Every row still runs sdist, wheel-from-sdist, and all 2643
cases (2513 pass / 130 expected skips), without changing timing flags or
observations. Every cheap, first-two full, and final full/hash/equality gate
remains. Exact maps, dispatch, coverage/CTracer roles (5 Windows / 4 macOS),
CLI ownership, natural drain, source/runtime preservation, archive headers,
members and RECORD validation are inherited unchanged. Guardian remains
`45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e`.

Stock final proof is `PASS_STOCK_REPLAY_FOUR_SHA_BOUND`, not the original
`PASS_ALL_FOUR_SHA_BOUND`. No within-job B comparison/threshold is calculated,
and the original cross-host B comparator rejects stock results. Storage
comparison is prospective across independent jobs (Windows C control, newly
prepared D Dev Drive, macOS control); this artifact neither dispatches those
jobs nor supplies a new statistical controller or benchmark result.
