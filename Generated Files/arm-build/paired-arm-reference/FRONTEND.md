# P40 portable supported-frontend cohort

Q-only preparation, not authority to execute or allocate resources. The prior
independent P40 audit is complete: **PASS WITH LIMITS**, high confidence in
retained timings/artifacts/source, medium confidence in transfer. Local native
preflight, new-code review and the finite CI decision remain with the parent.
This is a new frontend experiment, not a retry or retune of the three earlier
reference cases. No production/source/backend patch.

The existing registered workflow accepts `platform=matched-frontend` on exactly
`yeelam-gordon/fastapi`, `refs/heads/perf/hobl-arm-frontend`, manual attempt 1.
Only the existing Windows 11 ARM and macOS 15 matrix runs; analysis is excluded.
Old selectors retain their old reference ref and behavior; `both` remains the
default. No extra job, aggregation, SDK, CLI, full-suite, PDM candidate or
prefetch workload is selected. Bootstrap and five minimal build distributions
are reused without a new dependency/version/security policy.

## Frozen workload and limits

* Source: complete raw Git LF revision
  `864b569cf8453654fc3bc2c64108c0f644e2918c`, all 2,557 payloads proven against
  blob IDs, ordinary tar data-filter extraction, original metadata and modes.
* Both arms use official unmodified PDM 2.5.0 wheel SHA256
  `5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63`,
  separate singleton wheelhouses/caches, SDE `1700000000`.
* A: `python -m build -v --installer uv`, normal provided-hash Verify using
  `UV_CONSTRAINT`; not generic Require.
* B: verified native uv 0.13.6 `build -v`, exact native312 selector,
  `--build-constraints`, `--require-hashes --offline --no-index --no-config
  --no-managed-python --no-python-downloads --no-create-gitignore`.
  Neither `--sdist` nor `--wheel`: default **SdistToWheel**, not two direct
  builds. `--require-hashes` is not `--require-build-hashes`; no bypass.
* First: actual B frontend positive sdist hash probe, wrong-declared-hash cold
  probe, then wrong-declared-hash positive-seeded-warm probe. Only declared
  digests change, never wheel bytes; warm means naturally seeded URL/cache,
  not a fabricated same-key hit. Both negatives must exit 2 before backend
  hooks or payloads and report expected/computed digests.
* Then one complete untimed pair. Only success enables the fixed fourteen:
  warmups A,B followed by AB,BA,AB,BA,AB,BA. Six measured pairs, no retry,
  replacement, adaptive retune or automatic follow-on.
* 16 complete outputs / 32 full archives per host (probes are separate).
  Full existing comparator checks ordered members, every payload/header,
  RECORD, raw wheel identity and decompressed tar bytes. Only gzip bytes 4–7
  may differ. All originals must remain unchanged.
* Existing statistics: >=5% median saving, >=5/6 favorable pairs, both order
  groups positive, all correctness gates. Results do not automatically
  authorize another resource allocation.
* Each frontend subprocess has a 180-second ceiling; the existing job has a
  60-minute ceiling and three-day evidence retention. Stop at first failure.
  Logs and any produced distribution directory are retained byte-for-byte,
  including failures. No normalized or substituted outputs.

Observer reads are **only** for hash probes and the untimed B pair. No observer
is started for either warmup or any of the twelve measured samples. The timer
encloses only the subprocess call, with environment, extraction, log handles,
hashing, preservation, validation and receipts outside. Setup is not timed
frontend performance.

Every new frontend command records raw `perf_counter_ns_start` and
`perf_counter_ns_stop`; `elapsed_ns` and `wall_seconds` are derived from those
integers outside the boundary. `wall_utc_ns_before` is sampled immediately
before the start counter and `wall_utc_ns_after` immediately after the stop
counter, solely for chronology (UTC is not the duration clock). Formatting,
hashing and serialization follow those readings. No identity subprocess is
added inside the interval. Nonpositive monotonic intervals fail without retry.

All executed local Python helper imports are enumerated by module, relative
path and SHA256 in `helper-imports.json`, checked against `inputs.json`, and
rechecked after commands. This includes the controller's otherwise unused
`cpu_audit` import. Unknown helpers outside this directory or the selected
Python runtime roots stop. The portable comparator is the already extracted
`compare`/`frozen` implementation: no `transfer.py`, `fixture_receipts.py` or
other legacy research import chain is loaded.

Actual uv-written `get_requires_for_build_{sdist,wheel}.txt` JSON must be
captured as `[]`, corroborated by the actual raw logs' exact PDM-only selections.
Missing JSON or unknown inputs stops, never inferred empty from absence.
Transient PE/Mach-O, pyvenv config, installed payload and RECORD observations
are opportunistic on each host. Unsampled transient properties rely on the
hash-verified stock wheel metadata, explicit native312 selection and guarded
outer/base; this is **not** a claim of full portable transient attestation.
The native binary and actual Python machine/version guards are retained.
The actual child ABI/cache tag, pointer width and base interpreter must also
match native CPython 3.12. The complete outer file snapshot includes bytecode;
preflight snapshots it before any outer child invocation and checks preservation.

Cross-host five executable sdist script modes (`coverage.sh`, `format.sh`,
`lint.sh`, `test-cov-html.sh`, `test.sh`) and ZIP creator/header fields remain
explicit unresolved comparison gates, not waived or chmod-normalized.
Within-host equivalence never establishes cross-host byte identity.

Prior independent full-stock correctness is reused, not repeated:
Windows run `41002642194` and final macOS run `41007566488`, helper
`1ddfc4135`, each 2,513 passed / 130 skipped. Earlier installer measurements
are not P40 data. No Mac performance or equivalence claim exists here.

## Parent-only next local invocation (not executed during Q preparation)

Use the existing read-only native CPython 3.12.10 outer venv, local verified
stock wheel and uv, a **new absent owned root**, and optionally a local Git
repository already containing the pinned revision:

```powershell
& $NativeOuterPython -B $FrontendDriver --preflight-only `
  --root $FreshOwnedRoot --uv $VerifiedNativeUv `
  --stock-wheel $VerifiedStockWheel --source-repo $LocalSourceObjects
```

Omit `--source-repo` only to permit the normal public pinned-source fetch.
Preflight performs just three frontend hash gates and one untimed pair,
**zero fourteen-command series and zero full-suite/SDK/CLI workload**.
It reuses the already provisioned outer dependencies; no pip install, feed
override, dependency restoration or outer-environment mutation is requested.
All five minimal versions must be present; existing extra distributions are
inventoried and preserved. CI instead creates a minimal environment using
ordinary verified public PyPI; no private feed or local machine path is encoded.
PIP settings are not treated as UV settings.

High confidence: Q contract gates and existing source/comparator reuse.
Medium confidence: portable transient capture readiness pending actual local
preflight and independent review. Low confidence: new-host gains and cross-host
artifact identity until finite authorized runs supply evidence.

The prior local screen's retained 10.215409150 -> 6.503885050 seconds,
36.3326% reduction and 6/6 favorable pairs remain qualified historical P40
evidence, not a portable result. Its omitted transitive `fixture_receipts.py`
manifest coverage and elapsed-only clock receipts are not retroactively fixed
or remeasured; the unused legacy helper's current LF agreement does not prove
historical raw pre/post identity.

Q validation: 78 unit contracts (65 unchanged reference contracts plus 13 new
frontend contracts), Ruff check/format, actionlint 1.7.12, PowerShell parsing
of all ten workflow run blocks plus the unchanged bootstrap, and `git diff
--check`. Fixtures cover Mac transients/Mach-O, path spaces, native/ABI
negatives, unknown/missing hook JSON, cold/warm scheduling, no observer in
warmups/timers, raw failed logs, hosted guards, minimal-only setup and default/
old-selector compatibility, complete local import closure, and raw nanosecond
clock fields/order/positive elapsed derivation. No local frontend preflight,
build or timing was executed to obtain these Q results.
