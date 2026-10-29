# Analysis-only collector

This collector is not an optimization or benchmark. Every result, including
uninstrumented context, has `performance_eligible=false`. Existing CI's
2.178 s isolated / 1.949 s nonisolated build gaps remain historical context;
there is no matched actual-hook Mac timing and no local hotspot ranking here.

```
python collect.py --uv <uv-0.13.6> --source-checkout <git-checkout> \
  --wheelhouse <hashed-wheelhouse> --output <NEW-owned-directory> \
  --context-repeats 3
```

On Windows stage collector/platform code, uv, verified wheelhouse and Python
3.13.15 ARM64 on owned C: NTFS. All generated source/out/tmp/cache are under
the new output root. The source checkout supplies canonical original Git
archive `79cab5bed28b24d92c185d236feb33f5783dfeb3` and the existing independent
`candidate/validate.py`, `candidate/actual-manifest.json`, and
`protocol/owned_process.py`; these helpers are not modified.

## Passes and boundaries

One uninstrumented warmup, three uninstrumented context builds, then separate
resource/verbose, cProfile, importtime and tracemalloc builds. A native pass
delegates to `arm_diag_platform.native_capture(callback, private_directory)`;
unsupported safe capture skips its callback and is explicitly partial.
There are no retries. Each command is bounded to 120 seconds; no new build is
started within 180 seconds of the 25-minute job budget. Preparation, archive
extraction, inventory and verification are outside command clocks. The shared
owned uv cache starts empty and is warmed once; OS file-cache residency is
unknown. Source/out/temp and stock isolated environments are fresh each pass.
Python/uv/PDM override variables are removed, including inherited bytecode
overrides. Context has no injected startup hook.

Only the pinned hash-checked PDM wheel is exposed to offline `uv build` through
find-links. Default complete sdist then wheel-from-sdist semantics, project
configuration and installed backend/runtime files are unchanged.

Diagnostic children receive a dedicated `PYTHONPATH` containing only hook
files and the real stdlib-only platform module. Controller site-packages are
never added. `sys.orig_argv` is inspected only to classify the generated `-c`
command, not serialized. Command SHA256, role, PID/PPID, receipt identity and
flags are retained. The public CPython 3.13 `sys.monitoring` API observes the
generated command's `PY_START` to `PY_RETURN`/`PY_UNWIND`, including backend
imports. Entry additionally matches an independently compiled command's
bytecode/names/constants, not just another startup frame named `<string>`.
This compilation is bootstrap-only and its code is not serialized.
It does not replace exec, patch Python or wrap/modify PDM functions.
Only exception-unwind events remain globally enabled after entry; successful
returns are monitored on that one code object. Collector receipt-writing and
monitoring setup overhead are included, not estimated away.

Bootstrap/export boundaries and both preloaded-module lists are explicit.
Initial os/sys/time/helper imports precede the bootstrap timestamp and are
unassigned. Profiler setup and platform counter adapter prewarming happen in
bootstrap, so the profiles must not be called cold-process import profiles.
Snapshot reads enclose the command window and have their own recorded cost;
their self/all-thread user/kernel deltas are not full-family CPU or exact
wall partitions. Resource Python audit counts retain event names only, not
arguments; they are not kernel operations, physical I/O or scanner evidence.
Native counter semantics and lifetime memory peaks remain separate.

cProfile raw full stats stay private; validated JSON full functions, distinct
self/cumulative ordering and caller edges are exported after path redaction.
Importtime is enabled on the actual child by environment and its fd2 log is
redirected only at command entry. Early imports and export imports remain in
the frontend's unassigned log, never fabricated as per-hook timing.
Tracemalloc records current/window peak bytes plus end-live allocation sites;
end-live sites do not attribute the earlier peak.

## Coverage and privacy

Four required role start/end pairs are mandatory in every instrumented pass.
Additional/unknown roles are retained. Identity/mode/PID/PPID, monotonic
interval/elapsed agreement, failure status, flags and bootstrap/export ordering
are checked. PDM function profiles and identified hook calls must parse;
importtime requires numeric PDM rows; allocation receipts require byte units
and a valid current/peak relationship. Merely finding files is insufficient.

Missing platform code fails preparation, never invokes a production stub.
Missing metric support is null/unavailable and makes coverage partial. Missing
or failed role receipts fail coverage. Strict source and artifact verification
remain independent failures, including the five known Windows script-mode
artifact differences. Unexpected artifact membership is an error. Safe
results/logs survive failures; process ownership uses the existing supervisor.

`private_raw` contains original logs, source/output trees, raw pstats and any
native output. Only `upload` is publishable: structured identities/coverage,
public source/artifact manifests, sanitized profile data and explicitly
labelled redacted log copies. No recursive raw-directory copy or automatic
native trace upload exists. No full environment/PATH or generated command text
is serialized. Inventory comes from the platform module's explicit whitelist.
Default retention is three days; deletion/upload enforcement belongs to the
caller. Noncomplete reports return exit status 1, including known strict-mode
failures; do not turn that status into equivalence.

## First-pass validation and remaining integration gate

Focused stdlib tests exercise role classification, failed/missing/stale/end
receipts, nonadditive clock/CPU scope, unavailable metrics, redaction,
private/upload separation and all three profilers against labelled unit
children. Unit backend/platform doubles prove instrumentation machinery only,
not actual uv/PDM propagation. Ruff and static compilation are required.

Platform integration candidate: `fdaace345c8f53a855fb398ef764b9113ffb27d5`.
The full stock uv isolated PDM dry run, native Windows artifact/resource
receipts and all four role propagation remain an integration gate; no
production proof is claimed from a unit double. macOS remains runner-only.
Native capture remains explicitly unavailable until a safe supported
owned-workload exporter exists. No CI, trace, push or PR was run here.

Confidence: **high** in unit-tested receipt/privacy/status mechanics;
**medium** in intended stock-child propagation until the real integrated
dry run; **low/unestablished** in cross-platform causes or performance parity.
