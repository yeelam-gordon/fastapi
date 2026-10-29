# Platform receipts and native capability boundary

Analysis only; `performance_eligible` is always false. Interfaces:

```python
process_snapshot() -> dict
inventory(paths: list[str], output_dir: str) -> dict
native_capture(run_build, output_dir: str) -> dict
```

`process_snapshot` imports only stdlib, including in an isolated `python -I -S`
process. CPU seconds are `os.times().user/system`, self/all threads, lifetime
cumulative, never waited-child/family CPU. Start/end monotonic nanoseconds and
counter-query cost are explicit. Snapshots are sequential/non-atomic. Hook
owners must report their own interval and bootstrap/export overhead; the
adapter cannot infer a hook interval. Only cumulative CPU/I/O may be differenced.
RSS is a gauge; lifetime peak RSS is never subtracted.

Windows ctypes uses correctly sized handles, SIZE_T and unsigned 64-bit counters.
Working set and peak working set are bytes, not private committed memory.
GetProcessIoCounters retains its native operation/transfer names: process I/O
accounting includes non-disk I/O and is not physical storage throughput/latency.
Darwin `resource.RUSAGE_SELF` exposes block operations, deliberately **not**
Windows logical read counts. `ru_maxrss` stays raw with unverified native units:
the archived Apple manpage says kilobytes, which is not sufficient verification
of current macOS ABI behavior. Normalized peak bytes and current RSS are
unavailable, not zero. Mac runtime validation remains runner-only.

`inventory` writes `platform-inventory.json`. It hashes the current interpreter,
PATH-selected uv/Git/Node, and supplied files; reads PE/Mach-O architecture
headers (universal binaries list slices, not an assumed executed slice);
queries Windows current-process IsWow64Process2; records actual-path filesystem
identity, CPU/RAM, explicit CI/tool/cache environment fields, controller package
versions, compiler/config and zlib identities. Missing PGO/LTO recipe, codec
versions, physical storage class and canonical byte/mode manifest are explicit.
Controller identity does not replace actual isolated backend identity.
No recursive source capture, environment/PATH dump, network/auth probe, installer,
build or configuration/security change is performed.

Optional controller psutil is imported only inside inventory. Absence is fine;
it is never a hook dependency. The Actions Node receipt is separate from
PATH-selected Node. `ARM_DIAGNOSTIC_ACTION_JSON` accepts a JSON object with only
these optional string fields: `node_version`, `exec_path`, `arch`, `platform`,
`sha256`, `action_ref`, `image_os`, `image_version`. Other fields are discarded;
external receipts are partial/unverified. Home paths are explicitly redacted.
Do not pass private-source paths; hashes are identities, not upload consent.
Historical Windows console image `20261025.196.1` and bootstrap
`20261026.197.1` remain separate origins. Current metadata does not resolve them.

## Native decision: unavailable, not empty success

On this Windows ARM DevBox, non-recording probes found:

- WPR 10.0.26100 CoreSystem, `-help start` / `-help stop`: built-in/custom
  profiles, memory/file mode, optional named instances. No demonstrated
  capture-time filter/export recipe covering the actual bounded build tree.
- xperf 10.0.26100 help is available; presence does not establish a safe
  process-owned CPU/file-I/O summary pipeline.
- `sample`, `xctrace` and `fs_usage` are not installed here. Mac availability,
  permissions, template schemas, ARM symbol resolution and loss are unvalidated.

`native_capture` probes only help/identity for supported candidates. It requests
CPU, file-I/O and scheduling coverage, returns `partial` with all three
`unavailable` and detailed reasons, writes `native-capabilities.json`, and
**does not invoke the extra build callback**. The callback has no pre-launch
PID; attaching to this adapter's PID would miss actual backend children.
Tool help cannot prove descendant coverage or privacy-safe export. No new
supervision layer is added. No sampler/recording is started or stopped, and
preexisting recordings are neither queried nor cancelled. CI identity alone is
not authorization, permission or a validated owned-process export pipeline.

System-wide recording is prohibited locally. Any narrower follow-up requires
root agreement, an owned ephemeral CI job, offline public build window, supported
bounded commands, exact owned sampler PID cleanup, native schema/loss/interval
verification and reviewed owned-process-only summaries. Raw traces must stay
under `private_raw`, excluded from artifact upload; this implementation creates
none and returns an empty **summary list**, not a successful empty trace.
Do not install an ADK, rebuild uv, trace Defender, alter exclusions/UAC/trust,
or infer consent to stop another recording.

## Primary references checked before implementation (2026-10-29)

- [Microsoft PROCESS_MEMORY_COUNTERS](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters):
  WorkingSetSize and PeakWorkingSetSize bytes.
- [Microsoft IO_COUNTERS](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-io_counters):
  read/write/other operations versus transferred bytes.
- [Microsoft WPR CLI](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/wpr-command-line-options):
  recording profiles, unbounded file-mode warning, global stop/cancel behavior.
  CLI help was actually probed; no recording command was executed.
- [Apple archived getrusage](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/getrusage.2.html):
  self versus terminated children, block/cache distinctions and ambiguous-for-
  current-runtime maximum RSS wording.
- [CPython 3.13 os](https://docs.python.org/3.13/library/os.html#os.times):
  user/system seconds; no inference from children fields.
- xctrace candidate syntax was inspected in a third-party hosted Xcode-manpage
  mirror, **not accepted as runner capability or primary validation**. No Apple
  runtime is available here; local primary man/help verification is still needed.

Pinned uv 0.13.6 release `tracing-durations-export` is development-only, not a
default capability. The root's read-only `TRACING_DURATIONS_FILE` / cache-dir
probe emitted no export. `UV_LOG_CONTEXT=1` verbose timestamps identify log
events, not exact extraction/installation spans. No uv rebuild is proposed.

## Interpretation and confidence

Historical isolated/no-isolation Windows-minus-Mac gaps are 2.178/1.949 seconds
on different older CI hardware, with invalid input/artifact parity and no
matched phase CPU/I/O. New local receipts cannot establish their cause.
Compare actual matched stage walls and absolute differential seconds first;
then comparable hook CPU/counters, preserving overlap and unassigned residual.

- **High:** local Windows counter/identity semantics, stdlib isolation, privacy
  whitelist, explicit missing-native coverage and no recording/build invocation.
- **Medium:** portable schema and mocked Darwin/error paths; actual integration
  and runner metadata availability may expose gaps.
- **Low/unestablished:** Windows/Mac mechanism attribution, Mac runtime counters,
  native stacks/waits/I/O latency, family CPU, parity or optimization benefit.

Validation uses stdlib unittest (12 cases), existing Ruff check/format and static
compilation. `platform-evidence` contains only read-only local Windows identities,
self counters, capability results and validation metadata, not build profiles.
No package build or collector workload was run by this lane.
