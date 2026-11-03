# Exclusive hosted build ETW research

## Read-only recorder inventory

After the hosted elevated-token gate and `wpr -status`, the prepared pinned
reader calls `TraceEventSession.GetActiveSessionNames` (`QueryAllTraces`).
Session names remain private; the controller rejects the same known recorder
markers. No session is created, attached, stopped or cancelled by inventory.
Native errors remain nonzero, with `recorder_inventory/session_inventory`
reported explicitly. There is no empty-list fallback or ignored CLI failure.

This replaces `logman query -ets`, which failed before recording in native
run41683099307 with HRESULT0x80071069. The failed instance/cause is unknown.
Local non-elevated execution proves only caller-visible query behavior;
hosted completeness still requires the unchanged elevated-token gate.

## Current native decoder: Microsoft TraceEvent 4.0.0

Native captures now use the pinned standard Microsoft typed kernel reader in
`reader`, not tracerpt/XML and never a fallback projection. The XML reader and
old schema artifact names remain reference/rehearsal compatibility only.
Before any trace, `reader_prepare` requires an existing major-10 SDK/runtime,
restores locked dependencies through explicit `NuGet.MicrosoftPublic.Config`,
and builds without restore, build servers, node reuse or shared compilation.
`global.json` permits compatible 10.x feature bands, not just local 10.0.403.
No SDK installer or global NuGet configuration is used. CLI home/package/cache
directories and all logs are owned/private.

`reader_decode` runs the built DLL under the unchanged guardian, producing
private canonical JSONL and a private summary. Typed callback kind dispatch
preserves the actual provider/event ID/source class/version/opcode. Image-v3
is not relabeled v2; process rundown is never a measured birth. The existing
Python lifetime/thread/image/sample/file analysis consumes a small strict DTO
adapter. Unknown subjects cannot satisfy owned activity gates. Missing image
checksum/timestamp values remain null rather than fabricated zeros.

Typed header PerfFreq/ReservedFlags, source EventsLost and typed BuffersLost,
actual public SessionStartTime/SessionEndTime bounds and observed QPC extrema
are used. Only `calibration-reader.json` and `build-reader.json` are additional
public paths: fixed library identity, numeric clock/loss and bounded observed
schema/kind/static getter-field names; no global activity counts or raw values.
The prior capture proof and failed-stage diagnostics remain unchanged.

Local actual fixture proof: 179,474 binary events, nine/fifteen populated
typed v3 thread start/stop events, 79,528 IP/TID samples and 35 image-v2 loads.
Image-v3 is covered only by a focused semantic DTO case; native ARM64,
FileIO and scheduling runtime behavior still require hosted calibration.
Earlier narrative below describing tracerpt is historical, not the native
execution path. No R2 trace was retrieved or decoded.

Per-process-lifetime CPU sample and file-record counts reconcile to the
family totals without publishing PIDs. Parent edges retain the launcher/
runtime chain. After tracing stops, both complete package outputs must pass
source/member/RECORD checks and warmup-versus-traced semantic equivalence. research

Source only; **no dispatch is authorized by these files**. Parent reviews and
allocates the single registered `arm-build-diagnostics` workflow (400482741),
platform `hobl-build-etw`, branch `perf/hobl-owned-stacks-20261104`. All other
billable jobs are skipped; the job API gate permits skipped entries, not a
misleading `total_count == 1` requirement. Direct workflow dispatch is not
exposed on the reusable workflow.

The only capture context is one fresh GitHub-hosted `windows-11-arm` job,
attempt 1, capped at eight minutes. No shared/local capture, elevation, policy
changes, raw uploads, dumps, optional-tool installers or automatic retry.

## Executable path

`private.ps1` atomically creates a new protected owner+SYSTEM-only directory
using modern `FileSystemAclExtensions`. `preflight.ps1` checks the actual
elevated token, eight GiB free disk, built-in tools, API run/head/ref/runner,
one expected active job and idle WPR before managed-runtime setup. The
controller repeats the gates and checks native session names via `logman`.
Only uv 0.13.6 and normal-GIL ARM64 managed Python 3.13.15 are selected.

`screen.py prepare` is reused unchanged: original 2558-file LF manifest,
common patch, 82 runtime pins, exact wheels and constraints. Its source hash
check is repeated after the builds. All dependency output stays private.

The unchanged SHA-256-pinned `owned_process.py` runs every controller tool
and payload with strict natural drain. WPR starts the exact parent-owned
memory profile **before** the launcher spawns the actual root. The private
launcher receipt stores native creation FILETIME, QPC birth bracket,
frequency and end. Synthetic Python root and known child have independent
native anchors, CPU/file activity and a sleep.

One calibration capture must pass decode, zero losses, QPC-frequency/creation
mapping, root+known-child complete lifetimes, owned samples and operations on
the known calibration file. Only then: one complete warmup and one traced
`uv build` (sdist followed by wheel-from-sdist), no full test suite.

Each payload requests at most ten seconds; stop/merge is bounded to 60
seconds. This is **not a hard ten-second kernel recording quota**: guardian
cleanup/tool scheduling can extend the actual recording window on failure.
The analyzer rejects root intervals over ten seconds. Memory buffers are
256 KiB × 256 (64 MiB); post-stop ETL acceptance is 128 MiB, not a write
quota. Unique instance names are never reused; only a successfully started
instance may be stopped/canceled. No global cancellation. Failed start or
failed cleanup reports possible residual buffers and nonzero status; the
disposable VM's eight-minute teardown is final containment.

`tracerpt -of XML -rts` performs binary decode. Streaming `decode.py` uses
the numeric raw counter and actual frequency, never XML local wall-clock
strings or `-gmt`. PID+birth timestamps and native creation anchors establish
family membership; rundown records cannot establish birth. Thread subjects
and time-scoped image ranges map exclusive sample records to allowlisted
module basenames. Sample counts/fractions are **not CPU milliseconds**.
Known-module image checksum/timestamp/size fingerprints and relative
per-process lifetimes are exported, not absolute image addresses.

## Deliberate partial capabilities

Every successful analysis is explicitly `PARTIAL`. Root versus descendant
sample counts can distinguish root CPU from child CPU without claiming a
Python redirector/backend role from a missing image. Descendant and PEP 517
hook roles remain unknown; no command-line string is exported or guessed.
Process v4, Thread v3, Image v2 and PerfInfo/SampleProf v2 use the observed
classic kernel provider GUID. File/disk records require actual subject/IRP/
file-object fields; classic FileIo operation variants must pass the hosted
calibration. File-name/rundown records only map object names; they are never
operation starts. File-object delete/name updates prevent stale name reuse.

`file_operation_records` is a record count, not a deduplicated operation or
cost total. Full IRP begin/end correlation and verified scheduling-field
decoding are not implemented: file durations and ready/blocked time are
`UNSUPPORTED`, not zero. No overlap sum, critical-path claim, wall-minus-CPU
I/O inference or unsupported symbol-level attribution is produced.

Only exact `stage.json`, `calibration.json`, `build.json`, `capture-proof.json`,
`calibration-schema.json`, `build-schema.json`
and current typed-reader `calibration-reader.json`, `build-reader.json`
plus `calibration-modules.json`, `build-modules.json`
are uploadable. Capture proof retains ETL SHA-256/bytes and exact profile
SHA-256 after successful stop/size validation, before decode; absent slots are
null, and later analysis failure cannot erase proof. Missing proof does not
establish that no recording occurred.
Public JSON has fixed keys/enums, finite numeric bounds, allowlisted module
names, bounded row counts and a 64 KiB maximum analysis document. Raw ETL,
XML, command strings, identifiers, private paths, errors and receipts stay
private. Durable stage records contain fixed stage/tool enums, native code
and possible-residual-buffer flag, plus an allowlisted reason enum (never
exception text). Preflight sets the reason before each gate.

Parent-review corrections: calibration root/child write the same basename
under distinct PID-owned directories. Warmup archives are preserved privately;
after the actual trace is stopped, `build_artifacts` rechecks the verified
source manifest and existing `artifact_set` checks both archive sets, failing
closed. Lifetimes include parent indices, with earlier-index/time-containment
validation; child birth must fall in its parent's lifetime, but a complete
child may outlive that parent. Analysis includes all owned end timestamps and
still rejects intervals over ten seconds. Duplicate owned PIDs fail closed
rather than sharing image caches.
Caller `actions: read` is scoped to the ETW reusable-call job only.

After tracerpt completes, an independent bounded metadata reader writes
`calibration-schema.json` or `build-schema.json` before any owned analysis.
These sidecars contain only provider GUID/event ID/version/opcode, a static
task-label enum, TimeCreated attribute names and EventData field names, plus
numeric PerfFreq/ReservedFlags/EventsLost/BuffersLost/PointerSize when known.
No field values, identifiers, times or global activity counts are published.
Limits are 128 schema rows, 64 fields and ASCII identifier names up to 64
characters; over-capacity, rejected metadata or malformed XML is explicit
PARTIAL. Unknown header numbers are null, not zero. Stage failures add fixed
exception-type and missing-field enums; unknown keys become OTHER.

## Local checks (never record)

```powershell
python -B -m unittest discover -s 'Generated Files\arm-build\hobl-build-etw' -p test_etw.py -v
```

Tests use private project-relative scratch directories and fake tools; they
cover PID reuse/native-clock mismatches, schema poisoning, exact cleanup
authority, failed start/stop, skipped-job routing and real-format XML joins.
The parent readiness artifact records actual local fixture/guardian/ACL
checks. Hosted kernel capability remains a calibration gate, not a reason to
block review waiting for physical machines.

## Independently selected module mapping

After positive raw typed analysis/validation, the existing owner join observes
only accepted `(QPC, TID, IP, process_index)` records. These keys and original
per-lifetime counts remain in the owner/SYSTEM private directory; they are never
artifacts. A separate mode in the same pinned TraceEvent 4.0.0 reader converts
privately to ETLX and uses mature code-address/module tables. Raw births, native
clock, ownership and PID-reuse checks remain authoritative, not TraceLog process
association or rundown. No global PID selection is passed to the library.

Matching consumes the exact key multiset, including duplicate counts. Missing,
extra occurrences of selected keys, ambiguous multi-owner keys and lifetime/count
mismatches fail closed. Foreign samples are not analyzed or exported; conversion
may privately read whole-trace rundown/kernel tables. Kernel mappings use only the
PID-zero module table; user membership is consulted only for selected samples.
Ambiguous/missing mappings remain explicit `unresolved`. Public names are a static
allowlist (uv/Python/standard OS/filesystem modules), otherwise `other-user` or
`other-kernel`. These are sample counts and module provenance, never execution
mode, cause or I/O latency; scheduling/file durations remain unsupported.

Symbols are disabled by all three TraceLog options and child-only cleared symbol
paths; no SymbolReader/source lookup. Conversion caps at 500,000 events and runs
under the unchanged 110-second guardian deadline. ETLX acceptance is at most
256 MiB **after** conversion, not a hard disk quota. Default ordinary-idle
filtering is allowed only if every selected identity survives; a missing selected
TID-zero key fails just like any other missing key.

`calibration_modules` / `build_modules` and fixed `module_mapping` failure reasons
are explicit. Earlier positive analysis and capture proof survive module failure.
Only validated fixed-schema aggregates (at most 256 KiB) reach the two exact
allowlisted module artifact paths. All reader preparation still precedes capture.
Native ARM integration remains unproved until an explicitly budgeted hosted run.

Module reader known `InvalidDataException` failures have fixed exit codes:
71 `module_arguments`, 72 `module_selection_schema`, 73 `module_counts`,
74 `module_key_schema`, 75 `module_key_range`, 76 `module_multiowner`,
77 `module_stale_etlx`, 78 `module_trace_loss`, 79 `module_sample_identity`,
80 `module_stack_depth`, 81 `module_missing_stacks`.
Only those exact allowlisted messages are caught, without printing exception
text or values; the controller maps codes to the same fixed public reason enums.
Unknown exceptions/codes remain nonzero generic `module_mapping` failures.
No failed reader emits a success-shaped module document.

Each per-index module bucket also has fixed `sample_context`:
`PROCESS`, `DPC`, `ISR`, or `DPC_ISR`, derived only from typed
`SampledProfileTraceData.ExecutingDPC` / `ExecutingISR` getters. `NonProcess`
is the library's DPC-or-ISR flag, not an ownership signal. These contexts retain
the identical independently selected key multiset and counts. DPC/ISR samples may
interrupt an owned thread; their association is not process execution or cause.
`PROCESS` means neither interrupt getter is set, not independently established
privilege mode. Module provenance remains separate from sample context.

## Inclusive sampled-stack module presence

The same privately verified sample keys also select `sample.CallStack()`.
Each lifetime reports `with_stack`, `without_stack`, `stack_frames` and
`unknown_frames` (frames with no module). Missing stacks are explicit, not
zero-cost evidence. With-stack plus without-stack equals its original CPU
sample count; exclusive leaf sample totals and selection are unchanged.
If no selected sample has a stack, code 81 / `module_missing_stacks` fails
closed before calibration can authorize the real build. Earlier positive
analysis and capture proof survive; partial missing coverage remains explicit.

`stack_modules` counts presence once per sample for each
`(process_index, provenance, module, sample_context)` class, regardless of how
many frames repeat that class. Each bucket is bounded by its lifetime's
with-stack count. Inclusive sums can exceed CPU sample counts: they are
**not CPU time, latency, execution mode, driver blame or mechanism proof**.
Unresolved or ambiguous module provenance stays explicit. Frame/module tables
never establish ownership; only the independent raw analyzer's keys do.

The walk follows only `CodeAddress.ModuleFile` and `Caller`, at most 512 frames.
Overflow fails closed with code 80 / `module_stack_depth`, retaining earlier
positive analysis and capture proof. No function, address or private image name
is exported. No symbol reader or symbol lookup is used.

The stack-only static OS allowlist additionally admits `cng`, `ci`, `ntosext`,
`mup`, `rdbss`, `bindflt`, `cldflt`, `wcifs`, `wof`, `fvevol`, `storvsp` and
`wdf01000`, only with kernel-table provenance. The exclusive leaf allowlist is unchanged.
User-table images with these additional basenames collapse to `other-user`.
TraceEvent 4.0.0 retains `.sys` in module names (unlike `.dll`/`.exe`).
The shared leaf/stack projector removes that suffix case-insensitively only
for kernel-table provenance before static allowlist matching. Unrecognized
drivers remain `other-kernel`; user-table names are not suffix-normalized.
Everything else stays `other-kernel`, `other-user` or `unresolved`.
Existing exact module artifact paths carry this schema; no new upload route.
Local retained-fixture proof does not establish ARM workload coverage or cause,
and does not authorize or allocate another hosted run.
