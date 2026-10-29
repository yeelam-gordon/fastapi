# Fresh SDK caller isolation — experimental, not release adoption

```text
python isolated_build.py --uv UV --python BASE_RUNTIME --source SOURCE_COPY --source-manifest MANIFEST --out-dir ABSENT_OUTPUT --workers 1 --cache-dir CACHE --wheelhouse WHEELS --report NEW_REPORT.json
```

Workers are 1 or 3. Use native ARM CPython 3.13.15 and uv 0.13.6.
The backend lock contains the official PDM 2.5.0 wheel hash from
`../tooling.lock`, with no additional dependencies on Python 3.13.
`uv venv` creates a UUID-named, exclusively owned environment; `uv pip`
installs only binary wheels with hashes, no index, offline, without project
configuration. No `uv run --isolated`, environment reuse, pip patch, or
ensurepip substitution. User-site imports and inherited Python path/home
overrides are disabled. Only whitelisted environment changes are recorded.

One environment serves the SDK's sdist and wheel-from-sdist steps. This is
**not** standard two-hook frontend isolation and authorizes no release adoption.
The wrapper passes the original source path directly to the SDK; it does not
copy/filter source, remove backend scratch, or hide SDK preflight failures.
SDK safety walks, fresh metadata and payload reads remain inside its timed phase.

## Diagnostics, ownership and timing

Reports must be new and outside source/output. Phase logs are raw combined
stdout/stderr bytes, outside output; errors include original traceback and
subprocess exit code. Commands, clocks, safe environment changes, tool/lock/code
hashes, interpreter identity, absent-before and exists-after-cleanup are retained.
Output starts absent and must contain exactly two artifact files in `artifacts`;
SDK extraction state may also exist under the output root.
Every failure, including cleanup, is nonzero; cleanup errors append rather than
replace the original cause. Only the exclusively created environment tree is
deleted, never source, output, wheelhouse or cache.

Timeouts belong to the outer harness, which must terminate the **process tree**,
not only the wrapper PID, and retain its own raw timeout log. The wrapper has
no hidden timeout/retry. If interrupted while waiting, it terminates and waits
for its child (Windows tree termination; POSIX process group). A hard external
kill cannot guarantee wrapper cleanup/report finalization; the harness must
record that as failure, not infer successful cleanup.

Time the complete process externally: bootstrap, locked installation, identity,
SDK, cleanup and final report writes all belong to that wall.
`wall_seconds` inside the report excludes interpreter startup/final report
serialization and is diagnostic only. Independent correctness validation is
outside the measured process.

## Verification and explicit readiness blocker

`python -B -m unittest -v test_isolated_build` covers fresh environments,
offline/hash argv, raw subprocess failure, simultaneous cleanup failure, input
rejection and preserved reports.
`wrapper-evidence/readiness.py` stages hash-verified tools/wheels and canonical
Git archive source on C:, reuses the already managed native interpreter, and
prepares a stock B then S1/S3 sequence against one shared source. It independently
validates complete contents, full TAR/ZIP modes and RECORD against the actual Mac
binary oracle for 79cab5bed28b24d92c185d236feb33f5783dfeb3.
Existing readiness roots are preserved using a fresh owned child.
Do not run again until the master integrates the producer's SDK fix and schedules
the serial C: readiness check.

**BLOCKED: PC-001.** The first direct-source S1 succeeded (exit 0; outer wall
6.348292900s; complete 1269/65-member oracle PASS; environment absent before and
after), but left `.pdm-build` state. The readiness coordinator then failed its
source-unchanged assertion (exit 1). Its unmodified reports/logs/inventory remain
in `wrapper-evidence/initial-direct-source`. Independent review confirmed this
state makes a subsequent SDK preflight fail; producer repair is pending master
integration. Final wrapper repeat-S1/S3 and B-to-SDK readiness is **not passed**.

Before that coordination arrived, source-copy trials were attempted. Their raw
logs, reports, timings and inventories are retained in explicitly **rejected**
directories. The source-copy workaround and its tests were removed. None of those
successful trial builds validates the final direct-source wrapper. No current
top-level success summary is claimed. `wrapper-evidence/status.json` is the
authoritative disposition; it also records source/environment hashes.

The stock-B trial exits successfully but fails strict correctness on five script
modes, never waived or repaired. These are local readiness smokes, not paired
benchmarks, Mac performance, parity, scanner attribution, or release approval.
High confidence in mocked lifecycle/error coverage and first direct-build artifact
validation; shared-source readiness remains blocked. Backend private API coupling,
outer hard-kill cleanup and pending producer integration are explicit risks.
