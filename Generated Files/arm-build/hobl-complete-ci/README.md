# Optional paired complete-HOBL cohort

## Optional analysis-only covered-test boundaries

Manual choice `hobl-phase-analysis` runs **one** full covered-test invocation
on each existing native ARM64 Windows/Mac job. It is not a performance cohort,
has no build loop, warmup, retry or speed gate, and leaves the existing default
and paired schedules and `phase()` clock unchanged. Provisioning, pinned source,
runtime constraints and guardian identities are reused. The analysis job cap is
12 minutes, its child cap 300 seconds, and outer owned-family cap 600 seconds.

`phase_analysis.py` is a small adapter around the existing worker environment
and ownership path. It requires the complete 2557-file source manifest and the
original 2513 passed/130 setup-skipped outcomes, including each teardown report.
Each collected node must have exactly one protocol/setup/teardown span; only
passing report nodes may have a call span. Make/log spans must match the complete
report `(nodeid, when)` multiset. Variable nested fixture spans are not subjected
to per-test cardinality rules.
The byte-identical previously executed public-hook observer has a strict SHA256
gate. No configure wrapper, profiling callbacks or thread CPU timing are used.

Windows retains `python -m coverage run -m pytest tests`; Mac retains the
canonical `bash scripts/test.sh`. Both load the observer via `PYTEST_PLUGINS`,
without disabling normal plugins. Mac's script resets `PYTHONPATH`, so an owned
`BASH_ENV` shell function reapplies only the observer import directory when
calling the original `coverage` executable with its unchanged arguments.
Original tests, skips, coverage config and contexts are unchanged.

`analysis/summary.json` reports absolute collection/setup/call/teardown walls,
reporting, session finish, root/loop/protocol residuals, direct-child partitions,
top phase nodeids and fixture aggregation. All nanosecond fields must be integer;
one recorded caller thread, proper containment, nonoverlapping siblings and exact
exclusive conservation are mandatory. Fixture setup is a nested subset, **never
an additional setup cost**. Fixture finalizers remain in teardown/session finish.
The command wall outside the root is explicitly unattributed startup/shutdown,
not inferred CPU or OS cost. Instrumented values are never performance-eligible.

Complete collection nodes, all raw test phase reports and normalized boundary
spans survive as public analysis JSON. Absolute fixture paths are normalized;
raw thread IDs, guardian liveness/PIDs, raw SQLite and full saved coverage
context maps remain under `analysis/private`, outside upload globs. Untimed
postprocessing reads both fresh main/CLI parallel shards through `CoverageData`,
saves the complete union privately, and publishes context/association statistics
and its hash. It does not invoke a JSON coverage report or assume one database.
Dedicated postprocessing retains stderr and fails closed on any stderr output,
even with exit zero and valid JSON; this does not suppress main pytest warnings.
No cross-OS context equality is asserted; excluded timestamps/async pragma
line 79 can differ. Source identities must match before and after the command.

Failure logs and reports are retained and cannot become valid analysis.
The final public result requires the unchanged guardian's successful owned
natural drain. Local synthetic smoke evidence is readiness only: actual
both-host full outcomes and attribution remain a future manually authorized run.

## Paired performance mode

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
