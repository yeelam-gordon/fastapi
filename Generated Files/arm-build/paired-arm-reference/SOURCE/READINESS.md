# Paired compatible-reference preparation

## Status and authority

**LOCAL PRESENTATION FIX ONLY; no additional hosted job is authorized here.**
No native bootstrap, dependency restoration, full suite, performance series,
push, dispatch, default-branch change, workflow-state change or upstream PR was
performed by this worker. The new fix has not executed on Mac; the first hosted
attempt's successful native Mac bootstrap is distinct from its failed guard.

This is the original human-requested, finite, readiness-gated owned-fork CI work.
It is not a new upstream proposal or a requirement for new per-run human
approval. Publication and resource/readiness decisions belong to the parent. The initial
paired allocation and the single corrected Mac-only allocation have both been
spent. This request permits local readiness work, not another job or dispatch.

Branch: `perf/hobl-arm-reference`, based directly on last-published
`4ba888056a5e4f9316e03df99366836cc7c37fda`, not the research branch.
Only `.github/workflows/arm-build-diagnostics.yml` and this helper directory
change. The helper directory contains bootstrap/driver/guards, pinned-source
proof, extracted archive/statistics validators, focused tests, constraints,
two small owner patches, MIT licenses, this document, local attributes/ignore,
and one 192,962-byte losslessly gzip-wrapped frozen candidate (under 200,000
bytes). Unwrapping outside the clock yields the identical 200,273-byte wheel,
not a repatched/repacked wheel or a new candidate.
No source archive, local result, private query/header, credentials, user path,
research history or research bundle is part of the diff.

Exact relative paths under `Generated Files/arm-build/paired-arm-reference/`:
`.gitattributes`, `.gitignore`, `bootstrap.ps1`, `driver.py`, `guards.py`,
`source.py`, `compare.py`, `frozen.py`, `test_reference.py`, `cpu_audit.py`,
`cpu-hook/sitecustomize.py`, `test_cpu_hook.py`, `test_cpu_audit.py`,
`installer.py`, `test_installer.py`,
`macos-reference-graph.json`, `test_reference_versions.py`,
`test_help_presentation.py`,
`build-constraints.txt`, `reference-constraints.txt`, `owner-dev.txt`,
`cloud.patch`, `pdm-small-read-prefetch.patch`, `CLOUD-LICENSE.txt`,
`PDM-LICENSE.txt`, `pdm_backend-2.5.0-py3-none-any.whl.gz`,
and `SOURCE/READINESS.md`. The only other changed path is the workflow above.

## Existing workflow registration and bounded allocation

Read-only GitHub API checks on 2026-10-30 established:

- Owned fork: `yeelam-gordon/fastapi`; default branch remains
  `perf/windows-arm-build-experiment`, at exactly the base commit above.
  The local `origin` is **upstream**; it is not the publication destination.
- `arm-build-diagnostics.yml` is already registered and active. Every one of
  the 20 remote workflow blob IDs matched the audited base.
- The new case uses **existing input names**, not a new registration:
  `platform=matched-reference`, optionally `native_traces=false`.
  The prepared `platform=matched-macos` option is explicit manual Mac-only
  selection, not an automatic retry or a change to the paired default.
  `platform` still defaults to `both`; `native_traces` still defaults to true.
  Existing `both/windows/macos` analysis steps, source and behavior are intact.
  The matched driver does not import or run that historical collector;
  its new raw/data_filter/stat-mode proof does not resurrect the old mode oracle.
- A future parent-owned dispatch can address the existing workflow filename,
  explicit owned repository, and `--ref perf/hobl-arm-reference`, with those
  existing input names. No default-branch edit is needed to register another
  workflow. `matched-reference` was dispatched at `0712ba752`; the single
  corrected `matched-macos` allocation was used for `41004707015`. Those
  allocations are spent; the selector is not authority for another dispatch.
- Only the matched matrix allocates runners: `matched-reference` retains
  **windows-11-arm + macos-15**; `matched-macos` selects **macos-15 only**,
  with no Windows allocation. The analysis job is skipped before matrix
  expansion. There is no Linux/aggregation job, retry action or second run.
  The matched job also requires the exact fork/ref and first run attempt.
- Each job has a finite 60-minute ceiling, fails closed, retains partial
  evidence, and never repairs/replaces failed samples. The parent aggregates
  the two artifact sets offline.

### First hosted Mac guard failure and bounded correction

Run `41002642194`, Mac job `123890363719`, failed the reference-version guard
before any performance commands: **zero valid Mac performance samples**.
The original partial artifact/failure is preserved, not repaired or counted
as a new measurement. Windows job `123890362482` finished **SUCCESS** under
fail-fast=false at the original commit. Its valid results remain unchanged:
PDM-code did not advance; SDK-code and supported-installer met their gates.
No Windows tuning or repetition is part of this correction.

The actual Mac identity has 78 distributions: all 77 present Windows-reference
pins match exactly; only `colorama` is absent, and the sole extra is the
already-allowed `uvloop==0.23.0`. Native bootstrap/extension-architecture checks passed.
This was our Windows-graph expectation bug, not evidence of Mac ABI/performance
failure. Primary installed-wheel Requires-Dist metadata establishes:

- pytest 8.4.2: `colorama>=0.4; sys_platform == "win32"`.
- typer 0.27.3: `colorama; platform_system == "Windows"`.
- Pygments 2.21.0's colorama dependency is only its unselected
  `windows-terminal` extra; all graph references to Pygments omit that extra.
  Click 8.5.0 declares no Requires-Dist here, so no Click marker is invented.
- uvicorn 0.54.0 permits uvloop for its standard extra only outside
  win32/cygwin/PyPy, matching the pre-existing Mac-only extra policy.

Evidence: identity SHA256
`981eb6039e555b182b98507c71d3765a0ece1239b29f721216556dc53e2be39f`,
install-report SHA256
`a30cb23e639683c49279ecde8f22a1093544b9f0750a7fde6288190d0703ded3`.
The sub-3-KiB fixture projects only public package versions/source IDs, not
the raw artifact, logs, native paths or environment.

The correction permits only absent colorama in the **Darwin reference**
graph with the verified pytest 8.4.2 / typer 0.27.3 pins. A future parent-version
change must re-establish that marker policy. Windows still requires it;
a present Mac colorama must still be exactly
0.4.6. Every other missing/present-version/extra check stays strict. The
explicit minimal build requirements, all 78 constraint pins, original test
requirements/workload/oracles, and runner/package bootstrap remain unchanged.

That single corrected Mac-only allocation was subsequently used for
`41004707015`. Its budget is spent; this local follow-up authorizes no new
allocation. No bad-commit GH rerun, automatic retry, push or dispatch is
performed by this worker.

### Second hosted Mac stop: ephemeral terminal presentation

Run `41004707015` passed the colorama guard, all four untimed build/installer
comparisons, hash gates, origin/auth/owner proofs and original CLI tests before
stopping at raw `--help` equality. **Zero Mac performance samples** were taken.
Both failed raw captures remain unchanged: 3,701 versus 3,702 stdout bytes,
empty stderr; the same documentation hyperlink had OSC8 IDs `6941240` and
`11370988`. They are not filtered, normalized or retroactively accepted.

Primary pinned Rich 15.0.0 source explains this: `style.py` initializes
`count(getrandbits(24))` and emits per-process link IDs; `Style.render` returns
plain text before OSC8 construction when the color system is None.
`console.py` detects `TERM=dumb` and selects that None color system, even when
Typer 0.27.3 forces terminal rendering through GitHub Actions/color flags.
This is the supported presentation mode, not a private Rich patch, random
seed, disabled candidate feature or captured-byte cleanup.

Only the separate untimed help/version/cloud-help probes now copy their
environment and set `TERM=dumb` **before both arms are captured**. They still
compare full raw stdout AND stderr bytes with the unchanged comparator.
`cli_env`, timed covered missing-file CLI, build environments/commands,
full correctness and schedules are exact source-identical to the prior
commit. No global terminal setting or dependency/candidate change is made.

Actual native ARM64 CPython 3.12.10 proof, with the frozen Rich/Typer versions:
ten disposable untimed subprocesses, zero full suites/timed samples. A public
Rich OSC-capable terminal fixture emitted IDs `2706845` versus `7123241`;
`TERM=dumb` produced identical plain bytes in fresh processes. Real complete
SDK overlays A/B produced identical raw help (2,880 bytes), version (64),
cloud-help (3,062), with empty stderr. A genuine text change was rejected.
This Windows proof uses public `legacy_windows=False` only in its separate
Rich fixture; it is not a new Mac execution claim.

The proof used `-B` solely to protect read-only existing native inputs; that
flag is not added to CI probes or timings. All source/overlay/reference
package files, including existing pyc bytes/mtimes/modes, matched before/after.
The failed Mac capture hashes also matched before/after. Local-only evidence
is in ignored `.local/presentation-native-proof`; its RESULT SHA256 is
`008bbdcbf21d4fd1902da47a029fd537255b6118b6513a0e53cb867ee151b9f7`.
It contains local paths and must not be published as a raw bundle.

### Complete feature-push trigger audit

`build-docs.yml`, `test.yml`, `test-redistribute.yml`, and `zizmor.yml`
restrict push events to `master`; this feature branch does not match.
`detect-conflicts.yml` has an unrestricted push trigger, but the read-only API
reported it **already `disabled_manually`**. This worker changed no status.
The other 15 workflows have no push trigger (including both ARM workflows).

**Parent must recheck the remote head/workflow set and the existing disabled
conflict-workflow state immediately before publication.** If the unrestricted
trigger is active, publication is not demonstrated to stay within the budget;
do not disable it or blindly push. No automatic push occurs in this driver.

## Frozen inputs and meaning

- HOBL main `df120528374c0a5de5cb5a526175973d1ea2b53f` establishes the
  actual `python -m build` and covered full-pytest workloads.
- FastAPI 0.119.1: `864b569cf8453654fc3bc2c64108c0f644e2918c`.
  CI fetches this exact ordinary Git object outside the clock, then runs
  `git -c core.autocrlf=false -c core.eol=lf archive`. All 2,557 payloads
  must match their Git blob IDs and complete Git tree membership.
  Raw 0664/0775 member flags, ordinary data_filter 0644/0755 expectations,
  and actual stat modes are recorded separately. Windows 0666 is NOT
  POSIX-equivalent. No chmod, replacement extraction filter or mode waiver.
- CPython 3.12.10 on both hosts. Windows uses the official portable ARM ZIP,
  SHA256 `20a5b1a707d899ffdfc5e3086d7372f7cc95eeea344d48ae256047cb7075cf63`,
  plus the previously verified executable/DLL hashes and PE 0xAA64 guards.
  Mac uses pinned setup-python with explicit arm64: the live
  actions/python-versions manifest was checked and contains
  `python-3.12.10-darwin-arm64.tar.gz`, release `3.12.10-14343898437`.
  Mach-O slices, actual ARM64 execution and Rosetta state are checked.
  Universal2 is accepted when actually running native ARM64.
  These are distribution/compiler/hardware surrogates, **not** exact HOBL
  pyenv binary equivalence or physical 20-core/16-core hardware equivalence.
- Two separate venvs: build 1.6.1 / pip 25.0.1 / packaging 26.3 /
  pyproject-hooks 1.3.3 / colorama 0.4.6 minimal closure; and the untouched
  original source `[all]` plus `requirements-tests.txt`, constrained to the
  78-distribution compatible reference. AnyIO **4.14.2 is explicit**;
  the original default AnyIO 4.15.1 warning failures are not relabeled.
  CLI 0.0.32, cloud CLI 0.26.0, typer 0.27.3 and Sentry SDK 2.73.0 are fixed.
  Only upstream uvicorn's macOS-only uvloop dependency may be an additional
  distribution; its actual version/native wheel hash is recorded, not invented
  from the Windows freeze.
- Normal verified public PyPI TLS is used on GitHub, not the local corporate
  route. Exact-version availability on each runner remains a readiness risk;
  there is no silent fallback/downgrade/source compilation. Pip reports retain
  selected wheel URLs/hashes; installed native extension slices/hashes, tags,
  every resolved version and permitted platform extras are retained.
- Synthetic per-job HOME/config/temp/cache. No inherited deployment/auth
  credentials, custom Python/coverage/pytest hooks or private package index.
  Default bytecode, original warnings/plugins/settings/hash policy remain;
  no telemetry-disable switches, SDK-error suppression or timed profiling.

### Backend experiment

PDM backend 2.5.0, source `8c6653726f71afdb2059b44dc9c7706693e95be6`.
Stock official wheel SHA256:
`5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63`.
Frozen LOCAL candidate wheel:
`98048fc49ebd86884266e0b572d7ec5f7b1c571a206aa9cbecbac8c575433d28`.
Lossless storage-wrapper SHA256:
`6a508d629d16e07e17b8d4b464b39884da5e5ed31fac068d5cee6870383fa649`.
Both wrapper and inner-wheel hashes are checked before use.
Candidate `sdist.py`:
`50f0bad699bda95cfe58901f81f1dc30782a46d693efacbeb4ca64c58b434bb4`.
The 68-line owner patch and MIT license are retained. The candidate is never
repatched/repacked. Only that module and RECORD may differ; every RECORD and
other backend payload is checked, with actual local installed-source proofs.
Existing owner failure/cancellation tradeoffs remain open; this is not owner
acceptance or new fault/signal validation.

Both arms use exact native `python -m build`, default stdlib venv+pip isolation,
two exact pip backend selections and wheel-from-sdist, with singleton local
wheelhouses, direct SHA constraints, `PIP_NO_INDEX=1`, and SDE=1700000000.
Constraint/find-links environment values use encoded local file URIs so owned
paths containing spaces are not split by pip's list-option parser.
This is a **controlled local mechanism**, not unmodified network HOBL.
Untimed A/B correctness precedes 14 executions: A/B warmups, then
AB BA AB BA AB BA. Full member metadata/order/RECORD and raw wheel bytes
must match. Only gzip header mtime bytes 4–7 may differ; decompressed tar
bytes must be identical.
The installed build 1.6.1 default-selection probe requires a valid outer pip
and no virtualenv path; immutable non-bytecode minimal-venv files are checked
before every build, so this is not a hidden ensurepip/bootstrap fallback.

### Cloud SDK experiment and full correctness

Owner `fastapilabs/fastapi-cloud-cli`, MIT, tag 0.26.0:
`c89fd8ca549ed54c79a0db7ece3ba8bb256be148`.
Complete equal-shaped package overlays must match pinned owner Git/installed
stock bytes; only `utils/sentry.py` differs. Exactly two imports move after
the unchanged login/deploy-token early-return guard. B is a LOCAL variant.

Before CLI timings: owner targeted 10 passes, stock negative 4 failures /
3 passes, unchanged FastAPI CLI 2 passes under each arm, actual cold import
origins and all registered/sibling commands, auth/error propagation, and raw
`read_bytes()` equality of help/version/cloud-help stdout AND stderr.
Owner-only respx is hash-pinned in a separate target and never in timed CLI.

The measured command is the original covered missing-file CLI, expected
**exit 1 plus original message**. Its ordinary stdio/coverage I/O is inside
the clock, with distinct coverage files. It has its own A/B warmups and six
AB/BA pairs; no full-suite speedup or normal server-start claim follows.

One separate stock-only full coverage/pytest pass uses original verbose,
duration, warnings/plugins and source coverage settings. Raw shards are
copied even on failure, before combine/JSON can consume them, never mixed
with CLI trial shards. Canonical JUnit names/statuses (not just counts) must
match 2,643 nodes / 2,513 passes / 130 original Pydantic-v1 skips:
SHA256 `ef8e9cd5bf0d4a5b6ffb3389d61d75fbed44b2d84e2e2c4a268ff22a60b7f37d`
over sorted `(classname,name,status)` compact UTF-8 JSON.
SQLite/JSON must agree on 863 source files and 1,409 contexts.
Any platform difference is retained and stops the gate; it is not normalized
or forced into an original skip.

Correctness wall is **instrumented and non-performance-eligible**. The unchanged
validated LF SELF hook (SHA256
`35dc681fc09f34774c359826a61aa1376e352c973336085ab2bf176c5f6d9517`)
is injected only into this full pass through process-local PYTHONPATH and a
fresh owned receipt directory. It registers one early stdlib atexit callback;
each actual Python worker/covered CLI child records its own os.times user/system,
PID/PPID and orig_argv. No trace/profile callback, runtime patch or environment
dump is added. Existing startup hooks/tracing must be absent before injection.
The early callback runs after coverage's later-registered exit callback (LIFO).

`CPU-AUDIT.json` reconciles both raw coverage shard PIDs against validated
receipts, roles and the actual entry PID. A direct macOS entry may equal the
worker PID; a Windows redirector may instead equal the worker PPID. No
Windows-only inequality is imposed. Only observed Python SELF CPU is summed;
this is not whole OS-tree/non-Python CPU, and incomplete totals are null,
never a substituted launcher-only zero. Valid short-process zero is permitted.
All ordinary/performance commands reject SELF receipt variables or the hook
path; clean default environments also remove inherited HOBL_CPU variables.
Setup/queue/checkout/bootstrap, correctness gates and trials have separate
boundaries. Per-host statistics reuse the frozen 5% / 5-of-6 / both-order
gate, not a significance claim. No old CRLF/3.13/uv trial is pooled here.
All result statuses explicitly leave cross-platform artifact/mode parity
**NOT ACCEPTED**, even after within-host correctness succeeds.

### Third independent case: existing supported installer

The same two jobs now contain three separate cases, in fixed order:
PDM-code, supported-installer, SDK-code. **Each has A/B warmups plus six
AB/BA pairs = 14 commands**, so the explicit performance budget is **42
commands per host**, not another workflow/job or four-arm factorial.
Each case has separate correctness references, private arm caches and
statistics. The sole stock full suite remains one instrumented,
non-performance pass per job; it is not repeated for each case.

The added case is existing supported P13 capability, not a new code candidate
or a combination with PDM prefetch/Sentry changes:

- Both arms use the **same official stock PDM 2.5.0 wheel** (`5b8746...`).
  A is `python -m build -v`; B only adds `--installer uv`.
  Neither source pyproject nor build dependency closure is patched.
- uv **0.13.6** is an explicit absolute native executable, PE/Mach-O and
  SHA256 guarded before invocation. CI uses the existing pinned official
  setup-uv action; the owned copied executable must match Windows
  `ec27977d62b5f6091bce410a8e69d40d07541803314e0120905c0ad0affaa5cc`
  or Mac ARM
  `3996850e6d85e60b0142b40af4bd984822d65f736b52209921c47312450685cb`.
  No bare-path executable or managed Python download is used.
- Mac identity was established **as data only on Q**, without execution,
  from the official `uv-aarch64-apple-darwin.tar.gz` release asset, SHA256
  `60fbd5c8a1ed681845eea28d9d622fcde03c51e91a43465b64a1e17db1ed3472`.
  Its native ARM64 slice and binary hash above were verified; the archive was
  deleted afterward. This is not a Mac workload claim.
- Controls directly follow the completed Windows V2 protocol at
  `87349d256e4b001bf4367a4796277c0cab6b62e9`: A uses pip mandatory hash
  constraints/no-index. B uses **normal provided-hash Verify**, not
  `UV_REQUIRE_HASHES`, with the same direct wheel URL plus SHA fragment and
  `--hash` constraint. `UV_NO_VERIFY_HASHES` is forbidden. Both are offline,
  no-config, no-managed-Python, no-download, singleton-wheelhouse controls.
- Before correctness/timings, the three V2-style gates must pass: positive
  exact installed stock payload/RECORD plus empty sdist/wheel get_requires;
  wrong declared SHA rejection with cold private uv cache; the same rejection
  after a correct artifact has warmed a separate cache. Negatives require
  actual expected/computed hash-mismatch diagnostics and zero installed
  payloads; the real wheel is never altered.
- Verbose build logs must show exactly the closed original `pdm-backend`
  requirements, two 2.5.0 selections and complete sdist/wheel payload. The
  same unchanged full artifact comparator applies. Normal Verify is proven
  only for this closed input, **not generic Require for all future deps**.
- Encoded local constraint file URIs preserve paths with spaces. The pinned
  uv source `329bf9448afd9f9088d14a4d57fbc61eb454f117`,
  `crates/uv-configuration/src/requirements_input.rs`, explicitly converts
  file URLs to local paths. Actual native hash gates remain part of preflight.

Historical V2 Windows medians 14.5709307 → 9.52788325 seconds (-34.6103%,
6/6 favorable pairs) motivate this separate case; those data are **not
pooled** into the new CI estimates, PDM-code/SDK estimates or Mac benefit.
The historical V1 zero-trial stop remains untouched, not an invalid sample
in the new case. Independent review/publication remains parent-owned.

## Local checks and parent handoff

Completed on Q only, with TEMP/TMP/TMPDIR/PYTEST_TMPDIR pointing into private
owned Q fixtures, CPython 3.13.15 controller (not a claimed 3.12 workload):

- 65 stdlib contract/mocked tests pass, including native universal2/Rosetta/
  x86 guards; synthetic HOME/credential removal; literal CLI exit 1; raw
  CRLF-vs-LF inequality; backend identity/RECORD; Git-LF/executable-mode
  integrity; both raw build phase streams; stale/failed coverage preservation;
  canonical node identity rejection; exact 14-command schedules and one
  full pass; preflight excludes full pass/timings; two allocated runner jobs.
  CPU additions directly reuse the original three schema guards and test
  2/2 PID reconciliation, Mac direct/Windows redirector relationships,
  missing/invalid counters, legitimate smoke zero, startup-hook exclusion,
  process-local injection and benchmark-hook rejection.
  Installer additions check Require/Verify separation, bypass rejection,
  positive/cold/warm gate scheduling, exact closed inputs/hashed-URL selections,
  native-tool identity, installed RECORD boundaries and three-case budgets.
  The hosted Mac graph regression passes; Windows missing colorama, Mac
  wrong-present colorama, unrelated missing/version drift/extra, and minimal
  environment absence all fail. Matrix guards prove paired=2 and Mac-only=1.
  Presentation regressions preserve the timed environment byte-for-byte,
  require only a copied untimed TERM change, and still reject ephemeral
  terminal IDs and genuine changed text in raw comparison.
- Existing native Ruff **0.16.6** check and format pass; existing actionlint
  **1.7.12** passes; bootstrap PowerShell AST parses without errors.
- Static real Git archive proof passed for all **2,557** pinned LF payloads;
  archive was generated on Q and removed. No native build/test workload ran.
- The zero-context cloud patch was applied to the existing public owner
  archive on Q; resulting production helper matches the frozen candidate
  SHA256 `f89eea909f14f313dd2b774e0a77efb847ff9eb3d79ef809a60a395ba6a28f2c`.
  An actual ordinary pinned owner Git fetch/archive also proved all 170
  payloads, the sole package-file delta, and identical previously qualified
  owner-test source text. Both static input trees were removed afterward.
- `compare_outputs` is unchanged from the validated transfer, exact function
  source SHA256 `30a691036a22bb5e8a86ce99afdb894425b755073abaf06b3595935dcde6a526`;
  RECORD/full archive/statistics functions are extracted from existing P23.
- Git attributes/index supply LF files. An initial local patch check caught
  CRLF working-copy text; restoring only owned files from the staged LF index
  corrected it. A mocked coverage check caught an unclosed SQLite handle;
  explicit closing fixed it. A static fetch found Git's existing
  `safe.bareRepository=explicit` setting; ordinary non-checkout object
  repositories avoid implicit bare discovery without altering that security
  setting. None of these checks caused a workload retry.

After the parent grants the native resource handoff, the driver supports
`--preflight --build-python <absolute-existing-native-312-venv-python>
--test-python <absolute-existing-native-312-reference-venv-python>
--uv <absolute-official-native-uv-0.13.6>
--root <fresh-owned-root>`, launched with an actual native 3.12.10 interpreter.
Both venv identities are checked; they are not restored/reinstalled.
This performs four untimed build correctness commands (PDM-code A/B and
supported-installer A/B), all three installer hash gates, and portable targeted
CLI/owner gates and one `python -c pass` SELF-hook smoke, **no 14-trial series
and no full suite**. The smoke validates actual receipt/PID/counter shape,
does no busy-loop work and accepts legitimate zero CPU. It still fetches
pinned public Git inputs, downloads the exact stock backend unless supplied
locally as below, and restores only isolated owner-test respx. Do not run
during another worker's disk lease.
`--guard-only --root <owned-root>` checks just the actual interpreter.

### Preflight-only local acquisition

The original default path always used public PyPI JSON/files for stock PDM,
and deliberately replaced inherited pip-index settings with public PyPI.
That remains the **unchanged hosted-CI default**; it cannot solve this
DevBox's known blocked public distribution route by itself.

The narrow local preflight inputs are now:

- `--stock-wheel <existing-wheel>`: verify the entire body against frozen
  official stock SHA256 `5b8746...`, then copy it to the owned singleton
  wheelhouse. No stock JSON/file download is made on this route. The existing
  Q-side PDM screen `wheels/A/pdm_backend-2.5.0-py3-none-any.whl` was rehashed
  successfully, without running a native workload.
- Optional `--respx-wheel <existing-wheel>`: require the exact owner-locked
  respx 0.23.1 SHA256 in `owner-dev.txt`. Its original hash-required/no-deps
  target install then uses only local find-links and `PIP_NO_INDEX=1`.
- Without that optional wheel, **only preflight's owner-test respx restore**
  honors process-local `PIP_INDEX_URL`. It requires ordinary HTTPS with no
  URL credentials/query. Original `--require-hashes --no-deps
  --only-binary=:all:` remain. No certificate bypass, extra index,
  URL rewrite, resolver substitution or private CI default is added.
- Both local wheel options are rejected outside `--preflight`. CI setup,
  its fixed public stock URL selection, and all timed mechanisms are unchanged.

Exact invocation shape, **only after the parent releases the timing lease**:

```powershell
$env:PIP_INDEX_URL = '<approved HTTPS package index>'
& $ReferencePython $Driver --preflight --build-python $BuildPython `
    --test-python $ReferencePython --stock-wheel $StockWheel --uv $Uv --root $FreshQRoot
```

Bind the Python variables to the existing absolute native 3.12.10 venv
executables, `$Driver` to this `driver.py`, `$StockWheel` to that verified
existing Q stock wheel, and `$FreshQRoot` to a new owned output directory.
`$Uv` is the existing absolute native Q tool matching `ec27977...` on Windows;
it is never selected by bare PATH or downloaded during this local preflight.
Append `--respx-wheel $RespxWheel` only if an actual cached wheel is found;
never reconstruct a wheel from installed SDK files. No such wheel was found
in the two bounded Q-side SDK directories checked. C-side caches were not
searched and no approved-index request/native preflight was run during the
lease. Child index settings do not mutate global configuration; keep local
preflight logs local rather than publishing private feed-route receipts.

Remaining bounded uncertainties: the corrected presentation on an actual Mac,
downstream Mac full correctness/coverage/SELF receipts and timed cases.
Both hosted Mac attempts proved native bootstrap/dependency availability, and
the second proved the preceding untimed contracts; neither yielded performance
samples. Confidence is **high** for this local presentation fix, **medium** for
unexecuted downstream Mac behavior, and **unmeasured** for Mac benefit/parity.
Stop at local readiness: the previous one-backfill budget is spent and this
message grants no additional hosted job. Do not push or dispatch.
