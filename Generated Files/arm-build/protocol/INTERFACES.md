# Next-experiment implementation interfaces

This file coordinates independently owned wrapper and harness lanes. [PROPOSAL.md](PROPOSAL.md) owns the measurement/acceptance contract; this file does not authorize CI or release adoption.

## Frozen inputs

- Package source: `79cab5bed28b24d92c185d236feb33f5783dfeb3` through a separate checkout/archive, not the research tree.
- Runtime: native CPython 3.13.15; uv 0.13.6; pdm-backend 2.5.0.
- SDK: `candidate\build.py`, normal attributes, workers 1 or 3. Source and mode manifest are prepared once; metadata and all payload reads are fresh.
- Caller backend lock: PDM 2.5.0 with official wheel hashes; no patched pip/ensurepip or custom format writer.

## Wrapper lane owns `isolated_build.py`, `backend.lock` and wrapper tests

```text
python isolated_build.py
  --uv UV_EXECUTABLE --python BASE_RUNTIME
  --source SOURCE_COPY --source-manifest MODE_MANIFEST
  --out-dir NEW_ARTIFACT_DIRECTORY --workers 1|3
  --cache-dir TOOL_CACHE --wheelhouse OFFLINE_WHEELS
  --report SAMPLE_REPORT
```

The wrapper creates a unique fresh venv, installs the locked backend offline with hashes, invokes the SDK, and removes only its owned environment. Creation, installation, SDK execution and cleanup all occur within the outer invocation. The artifact directory must not exist initially. Logs/reports are outside that directory. Any failure or cleanup failure is explicit and nonzero; preserve original errors. Record environment identity/freshness, phase clocks, commands, exit codes and cleanup outcome.

Tool caches may be warm; caller environments may not be reused between samples. Record only whitelisted environment changes, not credentials. The caller/runtime code must not alter machine protection or global settings.

## Harness lane owns `measure_pairs.py`, `compare_pairs.py`, harness tests and workflow

Implement PROPOSAL's B/S1/S3 variants and fixed five-block order. S1/S3 invoke the identical wrapper above, differing only in workers. The parent monotonic timer covers the whole invocation. Baseline B retains normal standard uv isolation. Source/runtime/cache/temp/output are C:-resident on Windows.

Prepare canonical source bytes/modes once, record the source and harness identities separately, retain raw logs and per-sample artifact evidence, and stop on timeout without replacement samples. Use versioned reports rather than silently mixing the old two-variant schema.

Per-variant correctness is independent. A known five-script baseline mode defect is recorded as a failure, not repaired or waived; it does not excuse a candidate mismatch. All SDK candidates must match the independent source-specific oracle. Performance target failure is distinct from a broken experiment.

The comparison reports all per-variant ratios and best correct SDK configuration on each OS. SDK caller-isolated sample parity is not standard per-hook isolation parity or release adoption. Do not silently relax the contract.

Harness tests use controlled fixtures/mocked subprocesses. No C: smoke or performance loop until the wrapper lane has committed and the master schedules the integrated readiness check; this avoids concurrent disk-intensive tests.

### Owned lifecycle and clocks (arm-pairs-v4)

The harness calls `owned_process.run_owned(argv, *, cwd, env, stdout_path,
stderr_path, timeout=120)` and samples only successful `Receipt`s. It retains
the complete owned-family receipt, actual `command_wall` and separate
`infrastructure_wall`; comparison rejects ownership failure, survivors, timeout,
cleanup failure, errors or unavailable clocks. No ancestry-polling fallback exists.
Command timing starts immediately before target spawn, after supervisor/ownership
setup, and continues through target exit and owned-family drain. Thus wrapper
creation, install, SDK build and wrapper cleanup remain charged. Infrastructure
is pre-command ownership setup, not provision or command latency, and is reported
separately on both OSes. This version does not mix v3 timings into comparison.

POSIX targets, including every wrapper phase, must stay in the inherited owned
process group: no per-phase detached sessions. The wrapper fix and independent
helper review are integration prerequisites, not permissions to run measurements.

## Independent review lane

Review the portable SDK's real code and failure/configuration/path/mode/metadata guarantees, not just its successful golden build. Execute focused tests, including optimized Python where relevant. Report consequential findings with reproduction and confidence. Do not alter producers.

Each lane stays in its own branch/worktree, commits owned paths only, and neither pushes nor dispatches CI. The master integrates and owns the final readiness gate.

## Owned process-lifecycle addition

The independent PP003 review requires durable invocation ownership rather than a polling-only ancestry claim. A small documented Windows job / POSIX group helper is being implemented in its own lane. No process-name cleanup, undocumented resume API, private system tracing or new general-purpose supervisor framework is accepted.

Its trusted measurement boundary must cover the entire actual variant invocation, including caller environment creation/install/build/cleanup. Any separate supervision setup is recorded as measurement infrastructure on both OSes, not hidden package work. Missing ownership, a survivor or timeout makes the sample incomplete and stops the job; no replacement samples or parity claim.
