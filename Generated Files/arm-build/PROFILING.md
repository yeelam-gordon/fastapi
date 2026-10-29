# Profile the measured bottleneck, not the machine's core count

## Applied scope

[PERSONA.md](../PERSONA.md) owns the expert reasoning method; [GOALS.md](../GOALS.md) owns the performance targets. This document applies them to profiling tools and follow-on experiments. The current Cobalt 100 VM cannot prove a result for the physical Windows ARM device.

## Toolchain layers

| Layer | Tool | Purpose and limit |
|---|---|---|
| End-to-end packaging | `uv build` with explicit Python and backend constraints | Measures actual distribution creation; subprocess wall time includes its descendants |
| Python backend | Standard-library `cProfile`, `pstats`, `-X importtime` | Explains Python import/function cost; diagnostic runs are excluded from benchmark samples |
| CPU and process metadata | `psutil` | Records core and memory information; whole-machine utilization on a shared VM is not attributable exclusively to one build |
| Windows CPU/storage investigation | Existing `wpr.exe`, `wpa.exe` | Event Trace for Windows can reveal process CPU and I/O; may require elevation and can contain sensitive local paths |
| Tests, later stage | Existing pytest/xdist, `--durations`, collection timing | Measures collection and scheduling before choosing worker counts; CodSpeed runtime suites are not package-build timings |

Use the isolated experiment environment rather than modify the system interpreter. `provision.ps1` verifies native ARM64 and installs hash-locked tools. Python is already installed on this host; no redundant interpreter installation is necessary.

## Diagnostic backend trace

The direct PDM diagnostic was executed successfully on this host. It profiles backend work rather than just a frontend waiting on subprocesses:

```powershell
$python = 'Q:\fastapi\Generated Files\arm-build\.venv\Scripts\python.exe'
$root = 'Q:\fastapi\Generated Files\arm-build'
& $python "$root\profile_backend.py" --source "$root\results\local-01\source" --reference "$root\results\local-01\artifacts\prepare-baseline" --output "$root\results\profile-02"
if ($LASTEXITCODE -ne 0) { throw 'Backend profile failed' }
```

Each phase writes a `pstats` binary and a sorted text report, builds the wheel from an extracted sdist, and checks artifact equivalence against the timed baseline. These profiled durations exclude uv orchestration and do not replace end-to-end wall timings.

The optional benchmark `--importtime` diagnostic uses the separately installed `build` frontend. That frontend invokes backend subprocesses: profiling the frontend alone does **not** profile all PDM work. Do not conclude that backend functions are cheap because they are absent from a frontend profile.

## Windows trace safety

Run `wpr.exe -status` before recording. Do not cancel or replace an existing session: another user or diagnostic task may own it. Collect only when a measured bottleneck warrants tracing, and request appropriate permissions if elevation is needed. A typical dedicated recording uses `wpr.exe -start CPU -filemode`, executes one isolated build, then `wpr.exe -stop <explicit-output.etl>`.

Do not upload traces automatically. Review them for private paths and unrelated process activity first. Do not disable Defender, UAC, certificate validation or filesystem protections to improve numbers. High-performance power policy can be recorded as a confounder without changing shared-machine settings.

## Tests and physical-device follow-through

After package-build measurements stabilize, measure dependency sync and test collection separately. Keep the existing suite and compare a bounded worker sweep (for example 1, 2, 4 and 8 workers) using identical dependencies. Worker startup, duplicated imports and I/O can make 20 workers slower than fewer workers. Validate a chosen setting on both ARM systems before changing defaults.

On the physical Windows device, reuse the exact experiment revision and environment, connect power, record power mode/CPU/storage/memory, close unrelated foreground work where permitted, and rerun matched trials. A thermal or hardware mismatch is a reason to qualify the result, not a reason to claim an OS-wide speed difference.
