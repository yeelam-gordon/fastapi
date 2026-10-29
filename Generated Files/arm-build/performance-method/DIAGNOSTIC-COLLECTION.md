# Bounded differential diagnostic collection

Contract for the next analysis workflow, not authorization to execute it.
Analyze existing paired wall logs immediately. Two ARM experiments have already
been used; no new run until readiness and the existing CI-capacity gate pass.
Use small existing collectors/adapters, not a new benchmarking framework.

## Common interface and context

For each retained observation record: run ID, platform, source/config identity,
phase and parent, process role/PID and child coverage, interval, metric, value,
unit, aggregation (delta/gauge/peak/sample), clock, collector/version, analysis
versus uninstrumented role, and status/reason. Status is measured, unavailable,
incomplete or not-requested. Use null, not zero, for missing values. Capture
exit status, lost events and capture overhead; a file's presence is not proof
that it contains the intended process or interval.

Required normal-context logs on **both** platforms:

- Workflow/job/run attempt and runner label, actual image/OS build, architecture,
  VM/physical status, CPU identity if exposed, allocated CPUs and RAM; frequency,
  power and host contention only if observable, otherwise explicitly unknown.
- Source commit plus canonical input/archive hash, content and required mode
  verification; workload/config/lockfile hashes, backend and tool versions,
  native interpreter architecture, runtime distribution/build identity and
  relevant compiler/PGO/LTO receipts when available. ARM host is insufficient.
- Exact redacted command and arguments, project-relative paths, start/end and
  wall timer scope; build/phase raw samples, stdout/stderr, failures and timeouts.
- Declared isolation, network/offline policy, cache hits/misses, initial
  dependency/bytecode/filesystem/output state, warmup/repetition policy and
  which setup/startup/verification/test work is outside each clock.
- Explicit environment whitelist only: for example CI, RUNNER_OS, RUNNER_ARCH,
  ImageOS, ImageVersion, PYTHONHASHSEED, PYTHONDONTWRITEBYTECODE,
  PYTHONPYCACHEPREFIX and SOURCE_DATE_EPOCH. Record absent values; normalize
  user paths and inspect values before retaining. Add a named variable only
  for a declared hypothesis. Never dump all environment variables or PATH.

## Escalation matrix

Each row applies to both OSes with identical logical phase/metric semantics.
Candidates below require capability and permission probes on the actual
native ARM runtime/runner. They are **not** installed-tool guarantees.

| Layer / trigger | Windows collection candidate | macOS collection candidate | Coverage and comparison rule |
|---|---|---|---|
| 0: existing evidence, now | Existing stage wall logs | Existing same-boundary logs | Join identities; report unpaired phases; distinguish Actions step wall from build-only. No run required. |
| 1: phase elapsed | Existing monotonic wall timers | Same logical monotonic timers | Exclusive boundaries plus whole-build residual; child/parent overlap and concurrency explicitly mapped. Cross-host absolute timestamps need not align. |
| 1: user and kernel CPU | Process times via existing wrapper or GetProcessTimes | Existing wrapper or resource.getrusage | Seconds summed over threads. Include backend children, including exited short-lived processes; one parent process is not process-tree coverage. State self-only limitations. |
| 1: memory | Process working-set/peak counters, if accessible | RSS/peak resource counters, if available | Bytes after verified API unit conversion; distinguish current/peak, process/tree and private/physical. Never sum per-process peaks as a simultaneous tree peak or subtract lifetime high-water marks as phase usage. |
| 1: file/I/O activity | GetProcessIoCounters or existing scoped counter | Available resource/file counters | State operation/byte meanings and cache inclusion. Mac block-I/O counts are not Windows logical read calls/bytes. Retain distinct metrics unless equivalence is established; counters alone do not measure file latency. |
| 2: leading hook/import delta | cProfile around real backend hook; importtime on actual Python child | Same hook and importtime scope | Capture prepare-metadata/build-sdist/build-wheel only where actually called. Preserve call counts, self/cumulative times and callers; timers are declared. Import-only probes cannot replace real hook coverage. |
| 3: unexplained on-CPU delta | Available native CPU sampling with symbols | Available native CPU sampling with symbols | Bound to owned process tree/phase; record sample period, stacks, unresolved symbols/loss and count. Compare functions/categories and CPU seconds, not raw sample counts at different rates. |
| 3: unexplained wall/wait or metadata delta | Available native file-I/O and scheduling events/stacks | Available native file-I/O and scheduling events/stacks | Capture owned opens/stats/reads/writes, durations/errors and waits where supported. Separate metadata/data and cached/physical activity. CPU samples cannot explain off-CPU time by themselves. |

Scope cProfile using its documented callable interface around the *actual* hook,
or run the existing real Python entrypoint under `python -m cProfile` where that
covers it. A native frontend does not become covered by wrapping an unrelated
Python parent. Probe importtime propagation to each owned Python child;
`-X importtime` on the parent does not establish descendant coverage. Use
separate diagnostic passes if combined instrumentation obscures attribution.
Neither importtime nor cProfile output is a native CPU/file-I/O stack trace.

Resource evidence supports hypotheses, not shortcuts: CPU/wall can indicate
parallel activity or waiting but does not partition wall time in a process
tree. Large I/O counts do not prove device saturation, physical reads or
security-scanner cost. Check scoped latency/thread states and relevant USE
metrics only when the leading delta requires them.

## Coverage, safety and budget gates

1. **Before CI:** declare one analysis run's questions, selected phases/metrics,
   expected discriminating outcomes, artifact-size/time caps, permissions and
   stopping conditions. Probe capabilities without installation or privilege
   changes. Unit/static-check any collector change and do an owned offline
   local dry-run of boundaries, child capture, redaction, failures and output
   parsing before requesting budgeted CI. This document-only task ran none.
2. **Before interpretation:** identities, complete command and boundary map are
   mandatory. For differential CPU/function/I/O conclusions, both platforms
   must cover the relevant process tree and interval with comparable semantics.
   Report a coverage ledger with missing processes, events, symbols and units.
   Partial coverage permits only explicitly scoped observations; it cannot
   pass a mechanism-complete gate. No tool/permission means unavailable, not
   an empty successful profile. Do not retry indefinitely to fill every cell.
3. **Privacy before native tracing:** limit work to the owned offline project
   build. Native traces can capture system-wide process names, paths, command
   lines or unrelated activity even if the viewer later filters to one PID.
   Require a bounded window and owned-process/descendant filtering at capture
   where supported, or a reviewed safe-summary-only route with protected raw
   retention. If scope cannot be made safe under existing permission, stop that
   capture and mark incomplete. Do not upload raw native traces by default.
4. **No security changes:** no Defender exclusions/disabling, UAC weakening,
   drive-trust changes or permission escalation. No credentials/full environment
   dumps, private source/data uploads or public paste services. Only approved
   redacted project summaries may leave the machine; public research queries
   use public identifiers. Keep evidence in owned project storage with bounded
   retention; never write to temporary/system directories.
5. **After the single declared analysis run:** answer its questions, preserve
   failures/contrary evidence and report what remains unknown. End or return a
   separately justified narrow follow-up proposal; no unlimited retries,
   autonomous extra CI or instrumentation campaign. Uninstrumented performance
   confirmation is a separate, explicitly budgeted stage under METHOD.md.

## Additional checked primary counter references

- [Windows GetProcessIoCounters](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getprocessiocounters):
  specified-process I/O accounting, handle access and explicit failure result;
  not a disk-latency measurement.
- [Windows GetProcessMemoryInfo](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo):
  per-process memory counters and access requirements, not tree aggregation.
- [Apple archived getrusage](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/getrusage.2.html):
  self/terminated-child user/system CPU and block-I/O/cache distinctions.
  Archived maximum-RSS unit wording is not accepted as a current macOS ABI
  guarantee: verify local docs/runtime before conversion, otherwise unavailable.
- CPython resource and Windows CPU-time references are S7 in METHOD.md.
  The checked APIs establish candidate semantics, not ARM runner availability.
