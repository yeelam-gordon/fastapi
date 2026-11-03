# Exclusive hosted build ETW research

Per-process-lifetime CPU sample and file-record counts reconcile to the
family totals without publishing PIDs. Parent edges retain the launcher/
runtime chain. After tracing stops, both complete package outputs must pass
source/member/RECORD checks and warmup-versus-traced semantic equivalence. research

Source only; **no dispatch is authorized by these files**. Parent reviews and
allocates the single registered `arm-build-diagnostics` workflow (400482741),
platform `hobl-build-etw`, branch `perf/hobl-build-etw-20261103`. All other
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

Only exact `stage.json`, `calibration.json`, `build.json`, `capture-proof.json`
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
validation; duplicate owned PIDs fail closed rather than sharing image caches.
Caller `actions: read` is scoped to the ETW reusable-call job only.

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
