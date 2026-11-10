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
groups, 480-second driver envelope and one 12-minute Windows job maximum.
No tests, retries, extra pairs or automatic follow-up allocation.

Before provisioning, the workflow must validate a parent review bound to every
critical source hash. The existing manual dispatcher has one isolated input;
other modes are unchanged. Do not invoke provisioning on a local machine.

## What this can establish

- Warm-cache package-command timing on this particular hosted image.
- Whether a spare eligible NVMe disk and ordinary ReFS actually work there.
- Full artifact equivalence within the measured Windows cohort.

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
