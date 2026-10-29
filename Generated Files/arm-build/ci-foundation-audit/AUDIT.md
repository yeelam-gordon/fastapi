# Paired ARM CI foundation audit

## Disposition and correction

**Historical observations, not an accepted artifact-identical OS benchmark.**
Run [40814588064](https://github.com/yeelam-gordon/fastapi/actions/runs/40814588064)
used source `264cbad400c8336057a70b9b6a65bfdb4920321e`. Strict
`comparison-r2.json` rejected 58 wheel-content, 1,080 sdist-content and five
executable-mode differences. Later canonical-source fixes were LOCAL ONLY and
do not retrovalidate these numbers.

**Correction to the earlier analysis:** Windows-local hotspots alone cannot
explain a Windows–Mac gap. Local prototypes/profiles are not Mac CI profiles.
A shared 60-second phase on both hosts explains zero seconds of their gap.
This audit ranks measured absolute differences, not Windows-local duration or
large ratios on tiny phases. No OS, hardware, storage, compiler or PGO cause is
proved.

## Already knowable without new instrumentation

All following gaps are Windows minus Mac. Rows from different timing tiers
overlap and MUST NOT be added.

| Tier / phase | Windows seconds | Mac seconds | Gap seconds | W/M | Samples per OS |
|---|---:|---:|---:|---:|---:|
| Workflow: complete measurement step | 65 | 18 | **47** | 3.61 | 1 |
| Workflow: checkout | 19 | 3 | **16** | 6.33 | 1 |
| Workflow: native Python provision | 8 | 2 | **6** | 4.00 | 1 |
| Workflow: checkout post-cleanup | 5 | <1-second boundary | **5 coarse** | unavailable | 1 |
| Workflow: tools, excluding wheelhouse download | 4.636779 | 1 | **3.636779** | 4.64 | 1 |
| Normal isolated complete build, median | 3.1287605 | 0.95038975 | **2.17837075** | 3.292 | 7 |
| Dedicated/no-isolation complete build, median | 2.6786721 | 0.730164458 | **1.948507642** | 3.669 | 7 |

Workflow API timestamps have one-second resolution; a reported zero boundary
duration is **not** zero elapsed work. The 65/18 measurement step includes two
preparations, fourteen measured complete builds, source handling, artifact
validation and a separate diagnostic. It is not a single normal build.
The fourteen measured command walls total **42.0126715/11.782836918**
seconds (gap **30.229834582**). All 22 recorded command walls total
**52.8481434/15.449527502** (gap **37.398615898**).
The measurement-step envelopes also contain uninstrumented harness work and
coarse boundary residue: the remaining envelope difference of approximately
**9.601384102** seconds is **unattributed**, not an isolated causal stage.

Normal build sample ranges: isolated Windows **3.0023713–4.5876116**,
Mac **0.866558375–1.071929667**; dedicated Windows
**2.4283223–2.7355066**, Mac **0.695190083–0.798966292**.
All samples are preserved in `paired-timings.json`. Offline warm dependency
cache, not cold machine/cache; baseline/candidate order alternates.
Within-host isolation-removal median differences are 0.4500884 seconds
(Windows) and 0.220225292 (Mac). The observed cross-host median gap decreases
by 0.229863108 seconds and a 1.948507642-second gap remains. This is a useful
diagnostic contrast, **not an additive causal decomposition of differences
of medians**, and does not isolate a timed internal setup stage.

### Existing checkout substeps: absolute-gap ranking

Timestamped console groups already isolate these intervals:

| Phase | Windows seconds | Mac seconds | Gap seconds |
|---|---:|---:|---:|
| Checking out ref | 5.643389 | 0.414884 | **5.228505** |
| Setting up auth | 5.182392 | 0.294584 | **4.887808** |
| Removing auth within checkout | 4.368089 | 0.246550 | **4.121539** |
| Fetching repository | 2.723206 | 2.099250 | **0.623956** |
| Getting Git version info | 0.546544 | 0.057002 | **0.489542** |

These are nested log-marker intervals, not CPU measurements. In particular,
the fetch duration is not the largest checkout gap: existing evidence points
first to local checkout/auth command overhead, not a network experiment.
Exact source line ranges are in the machine-readable table. Command-rendering
`Run ...` groups are deliberately excluded as execution timers.

### Provision, job and scheduling boundaries

Python receipt command subtotal: Windows **4.4641674**, Mac **1.8025935**,
gap **2.6615739** seconds. Install Python itself is **3.508597 versus
1.536246958**, gap **1.972350042**. Provision wrapper boundaries (8/2)
are distinct from command subtotals.

Windows-only `pip download` wheelhouse export is **5.3632212** seconds;
its upload is **2 coarse seconds**. Both are excluded from paired build and
job comparisons. The additional Windows-only frozen-lock step (1 coarse
second) is also excluded. Raw observed job envelopes are 125/33 seconds and
are retained only as noncomparable context. The known-extra-excluded envelope
is **116.6367788/33**, gap **83.6367788** seconds: it still includes wrapper
residue, all experiments, smoke, upload, cleanup and scheduler tails, **not**
a pure build benchmark or an exactly controlled job comparison.

Read-only run API: creation/start `03:52:37Z`; jobs start Windows
`03:52:41Z`, Mac `03:52:42Z`: **4/5 seconds scheduling envelopes**,
gap **−1 second**. Queue-only delay and VM allocation/provision duration
are **UNAVAILABLE**, not zero. Run `updated_at` is not a per-job endpoint.

## Raw build logs and import diagnostic

Every `000`–`021` stdout/stderr pair on both runners was inspected and hashed.
Normal complete-build stdout is empty; stderr is retained with source/wheel
markers and per-file additions, but **has no per-line timestamps**.
Separate sdist, wheel, hook, compression, scanning and isolation-setup
durations are therefore **UNAVAILABLE**. Ordering alone cannot supply them.
See `log-coverage.json` for each argv, stream size, marker and addition count.
Both first normal-build stderr logs contain **1,334 file-addition markers**;
equal marker counts do not establish equal bytes, filesystem operations or
CPU work, especially with the retained content/mode rejection.

The exact diagnostic argv is recorded without normalization in both report
commands and `paired-timings.json`:

```
<native venv python> -X importtime -m build --no-isolation --outdir <diagnostic> <source>
```

Its source cwd matches each normal build's source. This is **python-build**,
not the measured **uv build** frontend. The one diagnostic per runner has
wall 3.9662438/1.06788875 seconds and includes instrumentation overhead.
Both stderr logs have exactly one import header, with 219/209 numeric rows.
Their matched context is the parent python-build invocation, **not** an
identified backend-hook process family. Neither stream has any `pdm` import
rows. `-X importtime` appears only in the parent argv; no evidence here
establishes backend child import coverage. Backend import time is UNAVAILABLE.

Summing exclusive self records only gives **0.234287/0.085801 seconds**,
gap **0.148486**. Cumulative values remain nested source data and are never
summed or combined with self. Unique matched module rows are paired; repeated
platform-probe rows (Windows posix/pwd/grp, Mac nt) are excluded from module
pairing, not silently collapsed. All numeric self rows remain in the
parent-total sum, including platform-specific rows.

Largest paired **self** gaps are `_hashlib` **0.003577**, `encodings`
**0.003496**, `packaging.version` **0.003492**, and `build._ctx`
**0.003444** seconds. These millisecond gaps do not establish the cause of the
~2-second normal-build gap. Do not subtract the parent diagnostic import sum
from normal-build medians or label its remainder a measured backend stage.

## Evidence coverage and runner identity

`collection-gaps.csv` inventories available/partial/unavailable CPU,
user/kernel, process-family I/O, memory, stages, toolchain, storage and runner
evidence. **Unavailable is never zero.**

Validated labels: Windows has **4 logical CPUs**, `ARMv8 (64-bit) Family 8
Model D49 Revision 0, MICROSOFT CORPORATION`; Mac has **3 logical CPUs**,
**Apple M1 (Virtual)**. This does not identify a Windows Cobalt SoC or either
physical host. Windows 11 build 26200 and macOS 15.7.9; native Python
3.13.15, uv 0.13.6, PDM backend 2.5.0. Compiler strings are MSC v.1944 and
Clang 22.1.3, not proof of optimization/PGO configuration or causation.

Windows runner-image metadata conflicts: console reports
`windows-11-vs2026-arm64` / **20261025.196.1**, while bootstrap
`runner_image` records **20261026.197.1**. Preserve both, do not choose one
as established provenance. Mac console/receipt agree on **20260907.0337.1**,
`macos-15-arm64`. Storage device/class, cache residency, CPU throttling,
user/system CPU, process-family I/O and memory profiles are not captured.

## Next analysis priority — recommendation only, no pipeline execution

1. **Build-gap coverage first:** before causal claims, enforce canonical
   source/artifact parity in the planned analysis-only paired diagnostic
   pipeline; preserve failures. Capture matched complete-build and actual
   sdist/wheel-from-sdist boundaries, isolation preparation, each backend hook
   with argv/PID/parent PID and monotonic wall time. Keep stdout/stderr raw;
   preserve process identity rather than interleaving unlabelled import trees.
2. Collect minimal per-stage **process-family user/system CPU and I/O counts**
   to distinguish compute from waiting. Preserve member/byte/work counts,
   cache policy and tool/interpreter provenance. Continue alternating repeats,
   report samples/ranges, and rank absolute paired gaps. Do not redesign build
   semantics merely to obtain a timer.
3. **Checkout/auth is already actionable for analysis:** inspect the existing
   command-level console surrounding the ranked groups before adding probes.
   Resolve runner-image discrepancy. Existing fetch intervals do not justify
   network performance experiments.
4. Only then add targeted backend imports, allocation profiling or OS storage
   traces if a measured gap supports that hypothesis. Do not turn on all
   profilers blindly. Parent import millisecond rows are not the first target.

## Reproducibility / scope

`audit.py` reads the retained root evidence read-only and writes only this
owned folder. `source-hashes.json` gives raw SHA256 and byte lengths for used
reports, harnesses, bootstrap receipts/logs, every per-command log, caveat
documents, API receipt and the preserved raw console. Paths in timing rows
are relative to `Q:\fastapi\Generated Files\arm-build\results\ci-40814588064`
unless they name a file in this folder. Console line references are 1-based.
`gap-priority.csv` and `paired-timings.json` rank within nonadditive tiers by
absolute seconds, with signed gaps, ratios, sample counts and ranges.

Confidence: **high** in extraction and missing-coverage findings; **moderate**
in descriptive ordering from one job pair; **low/unestablished** in causal
attribution and cross-OS parity. No new CI, profiling, implementation,
installation, trace or production/source changes were performed.

Validation: all 125 input hashes and byte lengths recomputed; all 245 paired
rows checked for median differences and descending absolute-gap ordering;
both CSV schemas checked. The raw console is 75,812 bytes, SHA256
`00e379f133cb5e6a61cb97f4fe4e550bbafe61abdcba16c58ee960da52834a66`.
Raw console whitespace is intentionally preserved, with whitespace checking
disabled only for that evidence file. The API receipt is also stored without
newline conversion so its recorded hash survives checkout. Ownership-only
staging and preservation of all 5,198 original skip-worktree entries were
verified before commit.
