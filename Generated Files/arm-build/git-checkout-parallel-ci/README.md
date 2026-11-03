# Git checkout component CI preparation

Fork-only manual/reusable `hobl-checkout-screen.yml`, also selectable through
registered diagnostics workflow 400482741 as `hobl-checkout-screen`.
Exactly two matrix allocations: `windows-11-arm` and the existing paired HOBL
label `macos-14`; six minutes each. No automatic dispatch or adoption.
The label is not architecture proof: the controller rejects a non-native ARM
Python/host, including an Intel Mac allocation. Do not silently substitute labels.

Tools/source checkouts and uv 0.13.6 managed normal-GIL Python 3.13.15 setup
are outside measurements. The preinstalled bootstrap Python is only a controller;
it needs Python 3.10+ already on PATH, but no packages or setup-python action.
The original SHA-pinned guardian owns uv, native controller,
all Git commands and stdin shims. Any unsuccessful receipt closes the screen.
No project dependencies, Git installation, authentication/TLS override, elevation,
global Git config, instrumentation capture, or full HOBL payload is used.

All 2557 canonical blobs are read before measuring. Four fresh local shared
no-checkout clones are prepared first. Lazy fetch is disabled for subsequent
commands. Exactly four actual detached forced checkouts run in ABBA order with
command-only workers 1,4,4,1, autocrlf=false, a common owned empty hooks directory,
the default parallel threshold 100, and equal relevant safe configurations.
Trace2 is enabled identically on every timed command. Source metadata/object
content and complete working files are verified unchanged after preparation.
All filenames, raw Git SHA1 blobs, index modes/stages, clean status and detached
HEAD are checked after each arm; executable bits are additionally checked on Mac.
Filters, symlinks, submodules, conversion attributes, sparse checkout and fsmonitor
are rejected, not ignored.

Both ordered pairs must independently save **at least 0.2 seconds AND 5%**.
A negative result closes without retries/retuning. A positive result is only
a host-specific component lead: not whole checkout-pipeline, physical-media,
Mac portability, or canonical full HOBL parity (32.233 vs 25.317 seconds) proof.
The runner's current Git is used and its bounded version/binary architecture
identity reported; Windows Git may be x64-emulated even with a native ARM host
and Python, and that limitation must accompany interpretation.
`gate_passed` is independent of protocol completion: a valid negative result is
retained with `gate_passed=false`; there is no automatic downstream action.

Raw stdout/stderr, Trace2, object lists, paths, command arguments, process details
and configs remain in owner+SYSTEM ACL storage on Windows or mode 0700 on Mac.
Only exact `checkout-public/result.json` and `stage.json` are uploadable.
Failure is a static stage/category and native code, never exception text.
Typed failures distinguish host, runtime, binary/layout, source commit/tree,
attributes, config, worker trace, file oracle, source proof and native commands;
launch additionally distinguishes missing Python, missing uv and private storage.
Action-managed initial checkout/setup output is outside the private measurement
protocol. No source/protocol file or machine-wide configuration is changed.

uv 0.13.6's pinned `crates/uv-cli/src/lib.rs`, `PythonInstallArgs` lines 6038–6046,
declares `no_registry` unconditionally with `#[arg(long, overrides_with("registry"))]`;
the flag is accepted on macOS too, so no platform workaround is needed.

Local validation (no checkout timing):

```powershell
python -B -m unittest discover -s 'Generated Files\arm-build\git-checkout-parallel-ci' -p 'test_*.py'
```

Recorded budget: one dispatch, two jobs at six minutes each, after local
readiness/allocation review. The hosted outcome is described below.

## Windows-only HOBL opt-in

Hosted run41692925086 passed both Windows component gates but failed the
Mac gate. The parallel HOBL workflow therefore exposes
`windows-checkout-workers=4` as an explicit Windows-only option. Its default
is `1`; Mac settings remain unchanged. The option adds only a job-local Git
configuration entry, retaining `core.autocrlf=false` and leaving global
configuration untouched.

The registered diagnostics workflow consumes this input only for
`platform=hobl-parallel-screen`. That mode runs the complete HOBL workload;
it was not rerun merely to wire this option. Component savings must not be
added to or subtracted from the separate HOBL build/test score, and the
complete checkout/authentication pipeline saving remains unmeasured.
