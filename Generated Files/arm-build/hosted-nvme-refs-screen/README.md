# Hosted ordinary-ReFS uv-cache comparison

This is a manual, owned-fork, **build-only** experiment motivated by
[actions/runner-images#14878](https://github.com/actions/runner-images/issues/14878)
and [Devolutions/IronRDP#2186](https://github.com/Devolutions/IronRDP/pull/2186).
It is not a new FastAPI build dependency or an upstream workflow change.

The reference PR uses automatically trusted Dev Drive formatting. This experiment
does **not**: it creates ordinary ReFS only on one eligible unused RAW NVMe disk
on GitHub-hosted Windows ARM64. It never uses trust/filter/protection overrides,
reformats an existing volume, or moves/junctions the workspace.
Missing or ambiguous storage explicitly prevents the benchmark.

Source/output/runtime remain C:, and TEMP/TMP are unchanged. Only the private
uv cache switches between equal-length C:/D: paths. Complete raw-Git source,
native Python 3.13.15, native uv 0.13.6, stock PDM backend 2.5.0, isolated sdist
then wheel-from-sdist, full archive headers/content/RECORD and natural process
drain remain required. The exact reusable guardian records the UV process from
its held launch handle; no custom PID poller or sampler is used.

`PLAN.json` freezes the question, two excluded warmups and six alternating
pairs, >=5% arm/paired median gates, 5/6 favorable pairs, both favorable order
groups, 600-second driver envelope and one 15-minute Windows job maximum.
No tests, retries, extra pairs or automatic follow-up allocation.

Before provisioning, the workflow must validate a parent review bound to every
critical source hash. The existing manual dispatcher has one isolated input;
other modes are unchanged. Do not invoke provisioning on a local machine.

## What this can establish

- Warm-cache package-command timing on this particular hosted image.
- Whether a spare eligible NVMe disk and ordinary ReFS actually work there.
- Complete member/content/header preservation under the explicit generated-time
  proof below; not byte-identical archive containers.

Provisioning/setup/audit costs are separate. One interleaved job is **not** a
baseline-versus-treatment whole-job comparison. Do not transfer the reference's
Rust result to Python, infer a Defender/filesystem cause, add old local gains,
or claim full HOBL, Mac or physical-machine parity.

Pure tests mock every storage mutation and benchmark launch; they do not prove
native Storage property binding or runtime speed. The first excluded warmup
must pass actual source/archive/lifetime gates before further commands run.

Support modules are byte-pinned copies of the existing qualified FastAPI
research protocol: `hobl-complete-ci` content/UV checks, matched-CI full archive
headers, and the b200 ownership/CLI-identity helpers. Their bytes are not reformatted
or regraded as newly qualified source.

## Runtime-output contract

The source passed focused review and the complete local phase-06 proof.
Hosted authority still requires a parent review bound to the exact manifest.
This does not regrade failed cases or qualify a performance sample.

Before WA, retain the complete runtime content/metadata manifest, source
associations and every preexisting `.pyc` byte sequence. WA and WB may produce
only canonical `cpython-313` default-opt0 caches for unchanged sealed source.
Replacements must have been stale by their captured original magic or
timestamp/size; rewriting a valid cache fails. New headers must have exact
magic, flags, source timestamp and size. The driver compiles the same source
bytes under the exact target Python 3.13.15 caller, with `dont_inherit=True` and
`optimize=0`, and compares the complete nested code structure and exact filenames.
It never executes those modules or precompiles caches for the build.

Warmup cache bytes before/after, associations and full manifests are retained,
not filtered from the evidence. Non-cache runtime files and source metadata
stay exact throughout. Runtime roots are bound to their resolved targets and
rechecked; links inside those roots, deletions, unsealed source associations,
noncanonical caches and unexplained directory writes fail.

After WB, seal **all** runtime files, including every cache. Check that full seal
before and after each measured command and at final audit. Nonruntime inputs,
including the actual build-constraints file and audit code, remain equal to
their initial hashes throughout. Retained raw evidence is also sealed.
There is no blanket `.pyc` exception and no source, timestamp, environment,
protection, guardian, archive, build-argv, schedule, budget or materiality change.

`execute` requires an explicit runtime guard. Production `main` must itself run
under the exact target interpreter (as the workflow's `TARGET_PYTHON -I -B`
already does); an administrative Python controlling another runtime cannot
provide compiler equivalence. A future diagnostic harness must construct this
guard explicitly; old readiness harnesses and their outcomes remain unchanged.

## Stock generated-metadata proof

The qualified `archive_headers.py` remains byte-unchanged. No raw archive or
header map is normalized. Every member, content hash and header field remains
exact against the first control except **only** the sdist member
`fastapi-0.119.1/pyproject.toml`'s `mtime` and PAX `mtime`.

Both reference and current must independently prove the stock PDM 2.5.0 profile:
finite numeric mtime; PAX keyset exactly `{mtime}`; and the PAX decimal equals
`Decimal(str(parsed_mtime))`. Its exact decimal value must lie within that row's
own native UV UTC window. The lower bound is
`(actual_process.birth_filetime - 116444736000000000) * 100` Unix nanoseconds.
The upper bound adds the qualified `native_end_ns - native_start_ns` duration.
Those native counters are QPC, **not Unix timestamps**. There is no added slack,
timestamp repair or alternate clock. Clock/window inconsistencies fail.

`SOURCE_DATE_EPOCH` is an unsupported ambient override: reject its presence,
never set or strip it. Other PAX keys, members, fields, content and all ZIP
metadata receive no exception. Full content/RECORD checks remain mandatory.
Different archive byte hashes are retained as observed, not repaired.

Each `generated-metadata-proof.json` binds the untouched header to its held
native PID/image/birth, command, native clocks, raw receipts/logs and retained
archive hashes. Row and final evidence seals include the proof and its inputs.
Case 04 remains **FAILED with two builds and no third launch**; this prospective
rule does not regrade it. Phase 06 passed both warmups, a strict-phase row and
all final seals. Its observed cadence conditionally placed build 14 after the
old 480-second envelope's reserve cutoff. Before any new hosted paired data,
the allocation is refrozen at 600 seconds/15 minutes; no failed run is extended.
Native 30-second/T+25 limits, 14 commands, six pairs, security and 5% gates stay
unchanged. Full hosted cost/value remain questions, not predeclared passes.

## Bounded audit I/O

Inventory reads use at most four workers, following the existing owned-guard
hashing pattern. Every entry, link check, before/after metadata check, content
hash and raw cache remains required; errors propagate. Ordered results preserve
the complete records. Pools finish before the next native command. This only
overlaps audit file-open latency outside the build timer; it does not parallelize
or optimize the FastAPI build.
