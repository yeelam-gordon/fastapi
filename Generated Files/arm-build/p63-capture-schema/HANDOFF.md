# Conditional ephemeral memory collector

## Result and scope

**SOURCE_READY_FOR_ONE_CONDITIONAL_BOUNDED_HOSTED_ATTEMPT, limited to capture
and report/schema validation; NOT diagnostic/cost-attribution ready.**

This source implements the existing memory route under the resource contract
in `P63-EPHEMERAL-RESOURCE-REASSESSMENT.md`. It does not change the original
cmdlet or memory-alternative BLOCKED results. Their saved file hashes are checked
in `verification.json`. No CI was allocated and no native recording, local
session status, token inspection, decoder, build, installation or policy change
was performed during this source work. All controller execution tests use fakes.

The production collection path can verify hosting, preflight tools/token,
prepare one offline build, start/readiness-check its named session, run that
build, stop, verify artifacts and invoke the decoder. It then validates the
narrow raw schema and report envelope. It **cannot turn that into an attribution
PASS**: complete circular-history/process-family coverage has no implemented
decoder adapter. That terminal result is UNKNOWN/nonzero, with only safe hashes.
A report envelope plus zero loss counters does not establish completeness.
The numerical positive projection is exercised with an explicit synthetic
coverage fixture only; production does not accept a flag or plan assertion
that enables that fixture's coverage assumption.

If a future job must deliver cost attribution rather than capture/schema
readiness evidence, **do not allocate this source as if that goal were ready**.
One separately reviewed finite job can instead establish native report
compatibility/schema facts and fail safely without claiming a Windows-gap cause.

## Actual source, pins and default

- `collector.py`: fixed-route controller, hosted proof, canonical-build adapter,
  private diagnostics, schema guards and positive finite projection.
- `private_report.ps1`: prospective token/tool/native preflight, private owned-root
  ACL, and assigned/all-stream-private Get-MpPerformanceReport invocation.
- `ENGINE-PROCESS-MEMORY.wprp`: byte-identical copy of the independently authored
  memory-alternative profile, SHA-256
  `8fd8f40086e86fceae92c6e765401607c2eb253b2467780f9a50a5681a7020d1`.
- `test_collector.py`: pure/synthetic control and privacy fixtures.

`python -I -B collector.py` emits source-only JSON and exits 0 without reading
authority, contacting GitHub, inspecting a token or launching any command.
The only collection entry is `--collect <private-authority.json>
<private-plan.json>`. Unrecognized arguments are not echoed. Source hash and
fixed categories/hashes are the only public diagnostics.

The Job guardian must hash to
`45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e`.
It is the published helper at
`Generated Files\worktrees\p50-cobalt-control\Generated Files\arm-build\protocol\owned_process.py`,
not the unverified main-root variant. The collector imports that verified
existing helper; it implements no new process/job/ETW framework.

## Authority and identity before native commands

The private authority must contain `approved: true`,
`scope: P63_ONE_EPHEMERAL_ATTEMPT`, repository `yeelam-gordon/fastapi`,
workflow ID `400167398`, exact current `run_id`, `job_id`, `head_sha`, `ref`,
`run_attempt: "1"`, `job_timeout_minutes: 8`,
`accepted_transient_overshoot: true`, an unexpired Unix `expires` no more than
30 minutes ahead, and SHA-256 `plan_sha256` for the exact private plan bytes.
No actual run/job authority is supplied by these source files.

Environment flags are supplemental, not hosting proof. The collector obtains
a live GitHub OIDC token over TLS without redirects; verifies RS256 signature
against GitHub's fixed JWKS endpoint; and checks issuer, audience, validity,
repository, event, ref, workflow SHA, attempt, run ID and
`runner_environment: github-hosted`. Its live GitHub REST run/job receipts must
match that signed check-run identity, current runner name, exact workflow path
`.github\workflows\arm-build-experiment.yml`, attempt 1 and `windows-11-arm`
label, without `self-hosted`; at least two CPUs are required. No saved caller
JWT or environment-only hosted claim is accepted.

All identity/API authentication finishes before capture. The actual future
workflow still needs separately reviewed OIDC/API permissions and an eight-minute
job timeout. This source does not edit or grant them. The default has no
network or resource effect. A durable per-run/job exclusive marker in the
current project directory prevents a second source invocation from retrying
collection in that job. The controller also rejects a second capture call.

## Recording, ownership and finite resource contract

The profile has two 32 x 1024 KiB fixed circular-memory collectors (64 MiB
configured aggregate buffers), Engine GUID
`0a002690-3839-4e3a-b3b6-96d8df868d99` with default all-keyword/default-level
selection, and kernel `ProcessThread`. No file-mode, CLR provider, stacks,
capture-state/rundown request or PDB-generation request is added.

Preflight checks the actual existing admin token without elevation, native ARM
process/OS, valid signed ARM64 WPR and MpCmdRun executables, actual versions and
the exact inspected ConfigDefenderPerformance 1.0 wrapper source hash
`a811d6b39943cd7f150287ac9b7f68ad9a6de8fd0c20d12cd10e59dfbb9c9921`.
A different/unsupported tool or module stops, without installation or fallback.
The only ACL modification is the newly created owned private directory,
protected for the current identity and SYSTEM; no global protection is changed.

Start uses the copied profile, no `-filemode`, a fresh 128-bit random instance
name, and a ten-second owned-command timeout. Only successful owned-command
completion followed by a durable fsynced start/context receipt permits further
session operations. Exact named status is queried before the build and again
before cleanup. Profile, memory mode, the two full instance-specific collector
names, 1024 KiB/32-buffer counts, Engine/process selection and loss-counter
shape must match. Missing/changed native status fields are unsupported and
stop, not inferred from a sleep or job-running state. This parser has not been
exercised on a live session. In particular, if this WPR version does not expose
the required actual buffer-count fields, the future attempt fails closed.

Every WPR session operation ends with `-instancename <owned-name>`. There is
**no cancel command**. An existing-session/start failure never sets ownership
and never causes stop/cancel. Cleanup requires the unchanged durable receipt,
current run context and fresh matching named profile/collector context.
Ambiguity causes nonzero failure and VM teardown, not a broad cleanup. A
positive loss counter fails the diagnostic but does not prevent stopping an
otherwise matching owned session. Failed stop is never retried.

The maximum requested recording window is 30 seconds from before start;
build command timeout is at most 20 seconds and further reduced by remaining
budget. Status command timeouts are three seconds, stop/merge at most 60,
decoder at most 60. Stop uses `-skipPdbGen`. The reused guardian has supervisory
and cleanup grace periods beyond each child timeout; these are not claimed
as an exact kernel-session lifetime. A kernel session is **not a Job child**.
Failed or ambiguous cleanup can leave recording buffers until the separately
configured eight-minute job limit and fresh-VM destruction.

The 128 MiB post-stop ETL limit (and private-report input-size limit) is an
acceptance check, **not a write quota**. Transient/output overshoot, merge memory,
intermediate files and disk failure remain accepted residual risks on that
single disposable VM. No old absolute-byte-cap result becomes PASS.

## One canonical offline build and oracle

The plan supplies `helper_directory`, `published_guardian`, `uv`,
`source_archive`, `source_proof`, `stock_wheel`, `baseline_directory`, and
`input_sha256` mapping full input paths to their approved hashes. All required
source/proof/stock/uv/baseline files must be hash-closed. It contains paths and
hashes only, never token values or arbitrary command strings.
It also supplies `source_sha256`, exactly the three executed source files
`collector.py`, `private_report.ps1`, `ENGINE-PROCESS-MEMORY.wprp`, checked against
the reviewed plan before any hosting request or native command.

The fixed helper import closure is pinned in `HELPERS`, using the frozen public
paired-arm-reference cohort associated with public head
`5603ed2218caff781f38698fd3baa558aa46eaf8`. Setup uses existing `source.extract`,
`frontend` native/source/backend guards and `frontend.constraint_text`.
Capture invokes exactly one existing `frontend.argv_for("B", ...)` command:
FastAPI 0.119.1, CPython 3.12.10, official native uv 0.13.6 and stock PDM backend
2.5.0, sdist then wheel from that sdist, offline/hash-closed.
No paired cohort loop, observation thread, tests, alternative version or
second build is invoked.

Temporary work, frontend caches, home/appdata paths and build output are under
the new owned project-local private root. Child environments are positively
constructed, not copied from the credential-bearing runner environment.
After stop, existing `frontend.verify_log`, `source.unchanged`,
`frozen.full_inventory` and `compare.compare_outputs` validate the normal
complete oracle, including archive members/metadata/RECORD, archive order,
decompressed tar bytes and wheel bytes, with only the existing allowed gzip
wrapper mtime difference. Oracle failure is nonzero, never diagnostic success.

## Static schema facts, runtime unknowns and projection

Readonly installed-wrapper/interface and formatting-property inspection found
an actual narrower contract; no arbitrary managed assembly was loaded:

- Raw TopScans rows are constructed with UInt64 `StartTime`, `EndTime`
  (FILETIME) and `Duration` (100 ns ticks); optional string `Path` is exposed.
- Optional `ProcessId` is Int32, derived by the wrapper from native
  `ProcessId` or `ScannedProcessId`. That is **not** parent PID or proof of a
  causal build-process family. No PID-family filter is invented.
- The wrapper uses native MpCmdRun JSON, not an established public managed
  decoder assembly/type contract. Raw Overview is dynamically projected;
  formatting metadata names StartTime/EndTime, but its complete field set and
  native temporal/coverage semantics are not statically established.

`schema-metadata.json` records these facts without proprietary implementation
or profile bodies. Runtime additionally verifies the wrapper hash and actual
UInt64/Int32 output types before privately serializing report objects.
`project` uses Windows path-component containment for the unique owned work
root, exact integer/range/time guards, a report envelope containing the build
interval and a strict TopScans count below 4096. Empty or at-limit results,
unknown scan fields, invalid/nonfinite values, missing envelope and absent
owned-path events all fail. TopN is never called a total. Unknown overview
values stay private; only schema-name/type hashes can be public.

Even a valid observed-path sample cannot prove both circular collectors
retained the complete build window or a process family. Production explicitly
keeps that final gate **UNKNOWN/nonzero**. ARM decoder support, reduced-profile
compatibility, actual Engine events and coverage must not be inferred from
function exports or fixtures. Scan durations can overlap and are not build
wall time, Defender causality, kernel open totals or Windows-gap attribution.

## Privacy, verification and exact publication boundary

All ETL, complete decoder output, command stdout/stderr, helper receipts,
paths, commands, errors and schema names remain in the protected owned root
until VM teardown. Decoder output is assigned and all its streams redirected
privately before inspection. Only fixed public keys/categories, safe source/
raw/error/schema SHA-256 and, in proven synthetic projection tests, positive
finite pathless counts/durations are emitted. Unknown property names/values,
process command lines, environment and raw errors are never copied to public
JSON or console. No raw bytes are retained as artifacts; raw hashes are
provenance, **not independent auditability without the bytes**.

The source public allowlist is exactly these five new files:
`collector.py`, `private_report.ps1`, `ENGINE-PROCESS-MEMORY.wprp`,
`test_collector.py`, `HANDOFF.md`.
`schema-metadata.json`, `verification.json`, `validation-history.json` and
`source-hashes.json` are local handoff evidence only. Future runtime publication
must allowlist only the specific `public-result.json` (or its safe stdout),
never a directory/artifact glob containing the private root. No root research
tree, authority/plan, raw log/ETL/report or installed Microsoft source is
allowlisted.

Pure tests cover positive fake controls, one-build/one-attempt enforcement,
authenticated hosted/API context, real RSA-signature fixture/tampering,
existing-session refusal, named/durable-context ambiguity, timeout/merge/loss/
oversize failures, first-failure preservation, complete fake pipeline ordering,
unexpected-secret error privacy, outsider paths, TopN/empty/missing coverage,
unknown secret fields, duplicate JSON and nonfinite values. Synthetic trace
file bytes are not a native ETL and are deleted with their owned fixture roots.
PowerShell was AST-parsed, not executed.

Validation command: `python -B -m unittest -v test_collector.py`.
**26 tests passed**; PowerShell AST parse errors: **0**; actual default
source-only CLI exit: **0**. All 12 saved original-result file hashes matched.
Ruff lint/format commands were attempted but the existing Python installation
has no Ruff module or executable; **not passed, no installation performed**.
`verification.json` retains final test output; `validation-history.json`
retains the tooling failure and corrected readonly metadata-probe failure.

Confidence: **high** pinned source/metadata and pure-control facts;
**medium** prospective controller/privacy lifecycle (not live-tested);
**low/unexercised** native decoder, named-status format and hosted integration.
Next bounded decision is source/privacy review of this exact allowlist and,
only if capture/schema validation is useful, one separately authorized fresh
eight-minute hosted attempt. No retries or additional allocation are implicit.

## Primary references

- https://learn.microsoft.com/en-us/defender-endpoint/performance-analyzer-reference
- https://learn.microsoft.com/en-us/windows-hardware/test/wpt/wpr-command-line-options
- https://learn.microsoft.com/en-us/windows-hardware/test/wpt/logging-mode
- https://learn.microsoft.com/en-us/windows-hardware/test/wpt/eventprovider
- https://learn.microsoft.com/en-us/windows-hardware/test/wpt/buffers
- https://learn.microsoft.com/en-us/windows-hardware/test/wpt/maximumfilesize
- https://docs.github.com/en/actions/reference/security/oidc
- https://learn.microsoft.com/en-us/dotnet/api/system.timespan.ticks
- https://learn.microsoft.com/en-us/dotnet/api/system.datetime.fromfiletimeutc

References retrieved during this source preparation and the immediately
preceding memory-route inspection on 2026-10-31. Named-instance syntax was also
observed in readonly installed `wpr -help advanced`; no live status was queried.
