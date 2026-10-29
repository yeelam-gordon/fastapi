# ARM build diagnostics: analysis-only contract

This lane explains the Windows/Mac gap. It is not an optimization benchmark,
release path or FastAPI dependency. `performance_eligible` is always false.
The method and evidence boundary are in `performance-method\METHOD.md` and
`ci-foundation-audit\AUDIT.md`.

## Questions, in order

1. What are the matched complete-build and actual backend-hook wall durations?
2. Which absolute Windows-minus-Mac gaps occur on the build critical path?
3. Do matched hook user/kernel CPU, import/function profiles, memory and I/O
   observations support compute, startup or filesystem hypotheses?
4. What remains outside observed hook windows, and which narrower native trace
   could resolve it? Unassigned time is not automatically setup, disk or MDE.

Existing CI has a roughly 2.178 s isolated-build gap and 1.949 s gap without
isolation, but no actual hook durations. Checkout/auth is a separate CI-latency
lead. Its 16 s checkout gap is not part of package-build timing. The 47 s
measurement-step gap includes repeated experiments and must not be added.

## Fixed inputs and separate passes

- Original source `79cab5bed28b24d92c185d236feb33f5783dfeb3`, canonical
  `git -c core.autocrlf=false archive`, complete source/byte/mode manifest.
- Native CPython 3.13.15, uv 0.13.6, official pdm-backend 2.5.0; hashed existing
  locks/wheelhouse. Default stock `uv build` sdist then wheel-from-sdist, with
  its normal isolation. No SDK, patched backend, patched runtime or selector.
- All Windows execution inputs/runtime/cache/temp/output on owned C: NTFS.
  macOS uses its owned job directory. Protection/trust/global settings unchanged.
- Preparation and cache warming are explicit. One context warmup followed by
  three uninstrumented context builds; these are analysis context, not parity proof.
- Separate single passes: resource/verbose hook timeline; cProfile functions;
  actual-child importtime; Python allocation/peak profiling; requested safe native
  trace. Do not mix profiler timings with context samples.
- Fixed bounds: 120 seconds per build, at most 25 minutes per job. No retries,
  replacement samples or automatic extra CI. Retain failures and partial data.

## Portable collection and scope

Capture exact redacted argv/cwd, source/tool/runtime/code hashes, native binary
architecture, compiler/version/codec identities, actual CPU/RAM/filesystem,
runner image and run/attempt/job identity. Capture PATH-selected Node/Git and
the Actions Node runtime separately; never infer one from the other.

Profile **actual isolated Python backend children**, not an unrelated parent.
A diagnostic-only startup hook may be injected through a dedicated PYTHONPATH;
project source/configuration and installed backend files must remain unchanged.
Normal context passes have no injected hook. Validate this propagation locally.

Required hook roles for pinned default uv/PDM are get-requires-sdist,
build-sdist, get-requires-wheel and build-wheel. Record PID/PPID, start/end
monotonic timestamps, wall/user/kernel CPU and scope. Additional roles are
retained, not silently discarded. Missing required roles fail coverage.

Minimize bootstrap imports. Record collector bootstrap/export boundaries and
preloaded modules; do not present a post-bootstrap profile as a cold import.
Resource-only hook windows are the primary hook-time context. cProfile self
and cumulative times/callers remain distinct. Importtime belongs to identified
children; early startup outside redirected child logs is explicitly unassigned.
Native frontend extraction/installation spans remain unavailable unless actually
observed; verbose timestamped logs do not automatically yield exact spans.

Retain memory current/peak scope and units, process I/O counter semantics and
Python audit/profile operation counts separately. Lifetime peaks are not phase
deltas; Python opens are not kernel reads or MDE scans. Unsupported metrics use
null with status/reason, never zero. No polling-based claim of complete family CPU.

## Coverage, native traces and privacy

Every collector is requested in analysis mode, but capability and permission
failures are explicit. Report `complete`, `partial` or `failed`, with a coverage
ledger; do not emit a blanket successful-mechanism conclusion.

Native CPU/file-I/O collection is a separate bounded pass. Probe actual native
tools first. No local system-wide recording is authorized by this contract:
live native system traces are CI-only on the owned ephemeral job. Never cancel
another recording. If safe owned-process capture/export is unavailable, record
the reason instead of weakening security or inventing data.

Raw potentially system-wide native traces stay in `private_raw`, excluded from
upload. Only reviewed owned-workload summaries go in `upload`. No credentials,
full environment/PATH dumps or raw command text containing tokens. All environment
fields are whitelisted. Offline build passes avoid authentication/network work
inside capture windows. Do not upload private local input data.

Normal safe logs, per-process public-code profiles, identities, code manifests,
errors and a machine-readable timeline/coverage report are retained in `upload`.
Record redaction when needed; do not relabel redacted output as original bytes.
Always preserve safe failure artifacts. Default retention is three days.

## Implementation ownership and interfaces

Collector lane owns `collect.py`, `hook\sitecustomize.py`, hook helpers and
`test_collect.py`. CLI:

```
python collect.py --uv <binary> --source-checkout <git> --wheelhouse <verified>
                  --output <new-owned-directory> --context-repeats 3
```

Platform lane owns `arm_diag_platform.py`, its tests and native-tool notes.
It must import using stdlib alone inside an isolated backend environment:

```
process_snapshot() -> dict
inventory(paths: list[str], output_dir: str) -> dict
native_capture(run_build, output_dir: str) -> dict
```

`inventory` may lazily use existing controller psutil. `process_snapshot` must
not expose controller site-packages to backend isolation. `native_capture`
accepts a no-argument build callback returning a JSON-compatible result; it
invokes it only if a safe supported capture is established. Unsupported native
capture may skip its extra build, but must return requested/unavailable status.
No new process-supervision framework; reuse existing bounded ownership if needed.

Master owns this contract, Actions inventory action, workflow, final integration
and comparisons. Workers do not dispatch CI or edit one another's files.

## Readiness

Unit-test metric units/statuses, role detection, missing/incomplete child
receipts, timeout/error preservation, redaction and privacy-safe upload selection.
Run a real local stock-build diagnostic and verify all required hook roles,
profiles, resource receipts and full artifact semantics. Preserve the known
five Windows script-mode failures, never waive them into strict equivalence.
Independently review integrated code and the analysis/performance separation.
Native Mac execution remains a disclosed runner-only gate. Freeze all inputs
before one budgeted analysis allocation; no current CI dispatch is implied.
