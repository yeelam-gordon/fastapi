# Full-HOBL parallel SCREEN (not adoption)

One manual dispatch, two native ARM jobs capped at 15 minutes each. Each uses
normal-GIL CPython 3.13.15, native uv 0.13.6, PDM backend 2.5.0, identical 82
runtime pins, and the exact previously tested 2558-file common source.
Windows has four workers, macOS three; actual logical CPUs must match.
The existing registered `arm-build-diagnostics.yml` entrypoint selects
`platform=hobl-parallel-screen` and calls the dedicated workflow; the new file
does not need to be added to the fork's default branch to register a dispatch.

Schedule: excluded serial/parallel full warmups, then measured AB and BA.
Every payload builds an sdist and a wheel **from that sdist**, then executes
the entire original full covered suite: 2513 passed, 130 skipped, zero errors.
Only worker count and stock loadgroup scheduling differ between arms.
Original function contexts and coverage subprocess/_exit flush are retained.
No tests, package work, or contexts are removed. No local cohort is rerun.

Raw streams, JUnit, shards, collection/phase/PID evidence, native identities,
source hashes/Git modes, config, downloaded-wheel hashes, archives and nanosecond
timings are retained. Hash/source proof runs once before/after, not per payload.
There is no HTML, full-context JSON, or per-payload archive expansion.
Only the final BA pair gets archive member/RECORD and reportable no-loss checks;
that audit has a single 60-second timeout. Failure or timeout stays a SCREEN
quality limit, never an accepted result. The original guardian owns the entire
cohort; natural drain must succeed and cannot be waived.

The test fixtures/group hook and guard correction are exact frozen inputs.
Observer/bootstrap adaptations remove local affinity binding, retain CLI/worker
trace evidence, and substitute native Mach-O checking only on macOS.
Runtime wheels are downloaded using normal TLS, checked against PyPI metadata,
then installed offline with explicit hashes. ujson is installed last at the same
pin because types-ujson and ujson overlap: not all RECORD ownership claims can
simultaneously hold. No global installation, tuning or security changes.

Two prospective pairs show direction only; hardware is not matched across OSes,
and two pairs are not the previous five-pair final-proof criterion.
