# Optional paired complete-HOBL cohort

## Optional maintained-runtime cohort

`hobl-paired-runtime` is a new, optional manual question: stock CPython
**3.12.10** versus candidate **3.13.15**, both using the same official native
uv **0.13.6** frontend and isolated PDM **2.5.0** sdist-to-wheel build.
Existing default/frontend modes and their phase clock are unchanged.
No SQL/native overlay, observer, profiling hook, omitted feature or new skip.

Exactly two 20-minute jobs use `windows-11-arm` and **`macos-14` ARM64**.
The latter is the documented standard ARM alternate in GitHub's
[hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
not a paid runner or automatic fallback. Both Mac runtime arms stay on that
same label. Actual OS/hardware/runtime identities are retained; this is not
a matched comparison with earlier macos-15 timings. A new label does not
guarantee capacity. There is no rerun, fallback or runtime-mode pip retry.

Windows stock retains the existing hash-verified PSF 3.12.10 portable archive.
Candidate 3.13.15 on both hosts, and Mac stock 3.12.10, use the same pinned
official setup-python action (`5fda3b95a4ea91299a34e894583c3862153e4b97`),
`architecture: arm64`, `update-environment: false`, explicit action output
paths and separate lexical venv executable paths. **Provisioning, including
Windows action ARM64 availability, remains a runner-only uncertainty**;
unavailability fails, not substitutes another release/architecture.
No invented archive hash or local runtime download is used. Before timing,
installed-payload probes require exact version, ARM64/64-bit, normal GIL,
no JIT, correct source import, native original coverage 7.17.0, compatible
WHEEL ABI tags and exact common package versions. WHEEL/RECORD identities
are retained. The uv executable is bootstrapped once with its distribution
RECORD gate. Platform-only colorama/uvloop pins remain platform-specific;
all within-host runtime-arm pins must match, without optional omissions.

Source is **FastAPI 0.119.1 plus one common test-helper correction**, not the
unpatched tag: `tests/utils.py` changes `> (3, 13)` to `>= (3, 14)`.
Preparation verifies the upstream committed blob, exact known old/new hashes,
patch bytes and a clean source checkout before writing. Original 2557-file
manifest/hash and the corrected manifest are retained: 2556 unchanged files
plus that one declared helper. The patch is `-text` for transport safety.
Both arms must report exactly **2513 passed, 130 skipped** every iteration.

Reuse of the existing schedule gives one excluded complete warmup/runtime,
then five **AB/BA/AB/BA/AB** pairs (10 measured rows/host). Dist remains
available during tests and is moved/audited only after full outcome/source
gates. Windows uses the unchanged coverage pytest command; Mac uses the
canonical `bash scripts/test.sh`, including its `PYTHONPATH=./docs_src` reset.
Arm-owned HOME/config/temp and version-tagged bytecode caches are separate.
Initially empty shared pip/uv dependency caches warm in the fixed order;
identical OS cache warmth is not claimed. Source content is common/frozen.
Only runtime and matching-ABI wheel payloads differ within a host.

Each iteration has a fresh private COVERAGE_FILE. Its **two actual main/CLI
shards** are merged in memory through public CoverageData APIs inside the
installed payload interpreter, never the clean base coordinator. Canonical
source-relative file identities (863), context identities (1409), exclusions,
and every reportable line/context association must agree. Raw oracles,
shards, warnings and all differences survive, including existing excluded
source-branch differences; no runtime-version whitelist. Original
`analysis2` exclusions alone classify differences; reportable loss or any
warning fails. Archive/RECORD/member/mode/source gates remain mandatory.

The worker's existing guardian has a **1100-second** runtime-pair deadline
inside the 20-minute job limit. `phase()` is unchanged. The worker result is
pending until the receipt succeeds with natural drain, no survivors/errors/
timeouts. Arm medians use actual complete build+test row totals, excluding
warmups, not added phase medians. Labels are stock/candidate runtimes, not uv.
Failure evidence is retained, never retried or replaced.

Offline unit/mock/tiny API probes establish local readiness only. Future
actual runner provisioning, full outcomes/oracles and performance remain
unmeasured. Existing local runtime evidence and maintained-uv evidence are
separate, not additive. This mode does not imply Python 3.13 is always faster.

## Existing frontend cohort

The manual workflow's default `hobl-complete` and `hobl-macos` modes retain
their baseline commands and five measured loops. `hobl-paired-uv` selects both
existing ARM hosts, with the same 20-minute job limit and no automatic rerun.

The optional `run_payload.py --paired-uv ABSOLUTE_EXE --loops 5` path uses
the existing phase clock, source, interpreter, identity, test commands, score
sum and process guardian. The stock command remains exactly `python -m build`.
The declared treatment is supported native `uv build --python ...` with
complete isolated sdist then wheel-from-sdist semantics, not wheel-only or
no-isolation. Both isolated backends are constrained to pdm-backend 2.5.0;
every wheel must attest `Generator: pdm-backend (2.5.0)`.
The stock arm copies the exact constraints bytes into its owned output and passes
that file's percent-encoded `file:` URI through `PIP_CONSTRAINT`. pip splits
environment constraint lists on whitespace (shell quoting does not protect
spaces); the URI preserves helper/output paths containing spaces without
changing the build command. The effective URI and original constraints hash
are retained in `paired-config.json`.

Preparation installs official `uv==0.13.6` through normal pip/index settings,
only in paired mode. `prepare_uv.py` resolves its bundled executable with
`uv.find_uv_bin()`, checks ARM64 PE/Mach-O identity and version, and records
its absolute path and SHA256. No persistent PATH change or extra action.
Its executable hash must also match the installed distribution's RECORD;
the module's global/user fallback paths are not accepted as bundled provenance.
The extra package is common to both arms of this **new** cohort; previous
baseline jobs are reference observations, not matched controls.

One complete stock warmup and one complete uv warmup precede five measured
within-host pairs: **AB / BA / AB / BA / AB**. All twelve rows and their raw
logs survive; only the ten measured rows enter per-arm medians. A complete
score is each iteration's actual build wall plus actual full covered-test
wall, not the sum of separate phase medians. Every warmup and measured row
requires exactly **2513 passed, 130 skipped**, exit zero and all 2557 canonical
source hashes unchanged.

Both arms share the same source, bytecode, runtime closure, home and scratch.
Initially empty pip and uv dependency caches are separately tool-owned and
warmed by their respective complete warmups. Source/test bytecode and OS cache
then evolve naturally in the fixed order; identical OS warmth is not claimed.
No tests, coverage configuration, plugins or skips are changed. There is no
observer. Tool/bootstrap work is outside phase timing.

Each iteration retains complete sdist/wheel bytes under its own artifact
directory. All member names, uncompressed content hashes, modes/types and
RECORD entries compare against the first stock archive set on that host.
Raw timestamp/compression identity is not required. Source payload ties are
checked; generated sdist pyproject TOML may only freeze the version and clear
the dynamic version list, while all generated bytes must still agree between
arms. Cross-host byte/mode identity is not assumed.

The existing guardian owns the entire worker/descendant tree, with a bounded
1000-second paired deadline. Successful scoring also requires its established
ownership, zero exit, natural drain, no survivors, complete cleanup and no
errors. An unsuccessful final receipt invalidates a prepared result. Failures
are retained and never retried/substituted.

Identity also records safe logical CPU count, OS/release and available
processor description before timing. Missing model information is explicit;
logical CPUs do not establish physical-core counts or matched hardware.

Local tests use tiny mocked complete workloads and tiny real archives, not a
local full-suite/performance cohort. Actual runner provisioning, outcomes,
archive equality and complete timings remain mandatory gates. No local
readiness result establishes a whole-HOBL speedup or Windows/Mac parity.
## Python 3.13 gap diagnostic (analysis only)

Manual `hobl-python313-gap-analysis` retains the accepted runtime pair's native
Python 3.13.15, Windows 11 ARM / macOS 14 ARM service classes, 80-pin closure
and common source (2,556 unchanged files plus the known `tests/utils.py`
`>=3.14` correction). It runs one instrumented covered suite per host, not a
build or warmup: source imports are already editable. Existing baseline,
frontend and runtime-pair schedules remain unchanged. No native-C, SQL,
empty-copy or renamer changes are applied.

The public-hook observer records wall and **caller-thread** CPU integer
nanoseconds per span. Wall reads surround CPU reads. Direct-child exclusive
CPU must be nonnegative and conserve the root exactly; malformed/nonmonotonic
trees fail closed, never clamp. CPU may exceed a tiny wall interval because
of OS accounting quantization: signed differences and overage counts are
retained, with a recorded 20 ms per-span tolerance and both clock resolutions.
This tolerance does not relax integer CPU-tree conservation.

Collection, setup, call, teardown, nested fixture setup, reporting, session
finish and residual ownership retain the proven per-node accounting.
Wall minus caller CPU includes waiting, I/O, other-thread handoff and
unmeasured work; it is neither process CPU nor worker CPU, and is not
automatically removable overhead. Fixture setup is a nested subset, not an
additional phase; finalizers remain in teardown/session finish.

Each child has 300 seconds, the unchanged SHA-bound guardian has 600 seconds,
and jobs have 12 minutes, with no automatic retries. Eligibility is always
false. Natural drain, complete ownership, no survivors/errors/intervention,
2,513 passes / 130 skips, exact observer/source identities, normal GIL/no JIT,
native coverage, and original coverage configuration are mandatory future
runner gates. A local synthetic probe cannot certify those hosted outcomes.

Private fork artifacts retain complete events, accounted nodes, reports,
stdout/stderr, ownership receipts, runtime/helper hashes, both raw coverage
shards and complete contexts. Canonical source-relative file/context mappings
and original `analysis2` exclusions permit independent reportable-line
comparison (863 files / 1,409 contexts expected); raw unexcluded cross-OS
equality is not required. Do not copy private IDs/absolute paths or logs into
public reports. This first-cold attribution is not an explanation of the
accepted cohort's warm medians, nor a performance/adoption claim.

After both future jobs, compare their private `canonical-coverage.json` files
with `phase_analysis.py --compare <windows-json> <macos-json>`. It rejects
different complete file/context/exclusion sets, preserves every raw
difference, and flags any reportable association difference separately from
original excluded-line differences. Keep this output private as well.
