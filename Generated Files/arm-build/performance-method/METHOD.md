# Differential build-performance method

Research checked 2026-10-29. This is a decision procedure, not a profiling
implementation or authorization to run CI. Start the existing paired stage-wall
log analysis now; do not wait for additional instrumentation.

## Evidence boundary

The supplied historical seven-sample, offline-warm build medians were Windows
3.129 s / Mac 0.950 s, and without isolation 2.679 s / 0.730 s. The comparison
was **invalidated** by input-newline and executable-mode differences. Local
corrections do not retroactively validate hosted results. Windows-only profiles
identify local costs, not the cause of the Windows/Mac gap. Matched Mac CPU,
I/O and function profiles are missing. Parity and foundational cause remain
unproven; physical-device parity is a separate outcome.

## Seven decision rules

1. **Establish comparability before attribution.** Join existing logs by source,
   command, phase boundaries, tool/runtime identities and cache policy, not just
   platform name. Verify canonical input bytes and required executable modes;
   preserve complete sdist-to-wheel semantics. Mark historical invalid pairs as
   exploratory. Separate provisioning, dependency setup, interpreter startup,
   isolation, package build, artifact verification and tests; distinguish
   job/step duration from the build timer. [S1, S3, S6]
2. **Rank differential seconds, not Windows hotspots.** For comparable phase i,
   report W_i, M_i, delta_i = W_i - M_i, ratio W_i/M_i, raw samples and spread.
   Rank positive, materially sized critical-path deltas first, retaining
   negative deltas. Windows 60 s / Mac 60 s explains none of the gap;
   Windows 20 s / Mac 5 s contributes 15 s. A 100x ratio on a 1 ms Mac phase
   contributes only 99 ms. Ratios with zero/unresolved denominators are
   undefined, not infinite evidence. Shared long phases remain independent
   optimization opportunities, not differential explanations. [S2, S5]
3. **Account for time once.** Use disjoint synchronous intervals or an explicit
   dependency timeline, with an unassigned residual. Parent/child hook clocks,
   cumulative import/function clocks and concurrent subprocess spans overlap:
   never sum them. CPU seconds across threads may exceed elapsed seconds.
   For each run, reconcile exclusive phases plus residual to whole-build wall;
   for parallel work, analyze the critical path, not summed work. Differences
   of medians are descriptive: sum(median(W_i)-median(M_i)) need not equal
   median(W_total)-median(M_total). Reconcile per-run totals, then summarize.
   Do not invent Windows/Mac sample pairing from unrelated trial numbers.
   [S1, S4, S5, S7]
4. **Ask one mechanism question, then collect matching evidence.** For a leading
   delta, first obtain wall and process-tree user/kernel CPU on both platforms;
   then scoped function/import profiles or resource counters as needed.
   Predominantly on-CPU work suggests CPU-stack analysis; unexplained elapsed
   time suggests scheduling/wait/file-I/O investigation, not automatic disk or
   Defender blame. Use USE (utilization, saturation, errors) and thread-state
   questions to avoid the streetlight anti-method. Same logical metrics and
   hook boundaries are required; native collection tools may differ. Missing
   measurements are unavailable/incomplete, never zero. [S2, S7, S8]
5. **Bound expected benefit and confounding.** For exclusive critical-path
   fraction f accelerated by factor s, the fixed-work upper model is
   speedup = 1 / ((1-f) + f/s); eliminating it saves at most f of elapsed time.
   This is an Amdahl-style algebraic bound, not a prediction from inclusive
   profile percentages. Re-evaluate the critical path after changes.
   ARM64 and 4 versus 3 vCPUs do not control per-core performance, CPU model,
   virtualization, filesystem, cache, power or runtime/compiler recipes.
   Report a platform-stack difference until a controlled contrast supports
   OS/toolchain causality; do not normalize elapsed time by core count. [S5, S6]
6. **Keep explanation separate from performance proof.** Label instrumented
   passes analysis-only; preserve exact commands, overhead, timer and coverage.
   cProfile is not a benchmark and does not automatically profile children.
   Profile actual build hooks, not an isolated import as a stand-in for the
   command. Fresh-process versus reused-process and warm/cold bytecode,
   filesystem and dependency-cache states are distinct conditions. Confirm
   changes with repeated uninstrumented full-command samples, raw values and
   spread; seven historical samples do not establish precision for a new
   small effect. Prefer alternating baseline/candidate order on each host;
   report host variation rather than asserting simultaneous paired machines.
   [S1, S3, S4]
7. **Adopt only evidence-backed, maintainable fixes.** Prefer a small common
   toolchain fix, then supported portable best practice; identify owner,
   compatibility/tests and review/upkeep burden. Reject private-PDM SDK hacks
   and framework expansion even if a prototype is faster. Apply relevant
   common optimizations to Mac too. Report absolute savings and new W/M ratio:
   a shared improvement can be useful without narrowing the gap, and a worse
   ratio does not by itself mean the absolute gap grew. Neither means parity.
   Follow collection/privacy/readiness gates in DIAGNOSTIC-COLLECTION.md.

## Completion gates

- **Existing-log analysis complete:** comparable phase table or explicit
  missing/invalid cells; raw provenance, overlap map, per-run reconciliation,
  leading deltas and uncertainty. This can finish before new telemetry.
- **Mechanism supported:** leading delta linked to a testable hypothesis and
  comparable scoped telemetry on both systems, with coverage and contrary
  evidence disclosed. Correlation alone is not OS/scanner/compiler causality.
- **Proposal ready:** predicted material full-command benefit, common owner or
  portable supported option, semantic proof and local readiness checks pass.
- **Goal verified:** fresh authorized native ARM64 uninstrumented comparison,
  canonical inputs and strict artifacts, best applicable configurations on
  both hosts, Windows median <= Mac median under a declared sampling and
  uncertainty policy. Overlapping uncertainty leaves parity inconclusive;
  build-only cannot establish setup/test or physical-hardware goals.

## Primary sources and checked coverage

These are source-backed method references, not claims that tools are installed.
Python 3.13 pages fix the documented semantics; use actual runtime-version
documentation before execution.

| ID | Primary source | Checked claim / boundary |
|---|---|---|
| S1 | [CPython profiling](https://docs.python.org/3.13/library/profile.html) | cProfile call counts, self versus cumulative time, actual callable scoping, overhead; explicitly not benchmarking. |
| S2 | [Gregg: methodology](https://www.brendangregg.com/methodology.html) | Problem/workload characterization, drill-down, synchronous time division, scientific hypothesis/prediction/test; warns against tool-led fishing. |
| S3 | [pyperf: running](https://pyperf.readthedocs.io/en/latest/run_benchmark.html), [system](https://pyperf.readthedocs.io/en/latest/system.html) | Processes, warmups, raw values, system noise/topology. Linux affinity/tuning and documented Windows priority are not permission or recommendations to alter shared hosts. No pyperf installation required. |
| S4 | [pyperf: analysis](https://pyperf.readthedocs.io/en/latest/analyze.html), [CPython importtime](https://docs.python.org/3.13/using/cmdline.html#cmdoption-X) | Distributions, median/MAD, comparison; import self/cumulative clocks and multithreading warning. Does not validate seven-sample causal inference. |
| S5 | [OpenCilk concepts](https://www.opencilk.org/doc/tutorials/opencilk-concepts/) | Work versus span, dependency DAG, critical-path lower bound and processor limits. No Cilk tooling proposed. Amdahl formula above is directly derived from fixed unaffected/affected fractions. |
| S6 | [GitHub runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) | Public Windows ARM: 4 CPUs/16 GB; Mac ARM: 3 M1 CPUs/7 GB; VM and label/image distinctions, runner identity in logs. Published specs are not actual-run CPU-model proof; private Windows specs differ. |
| S7 | [CPython resource](https://docs.python.org/3.13/library/resource.html), [Windows GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) | User/system CPU; waited-child accounting versus single-process accounting; Windows summed thread CPU can exceed wall time. |
| S8 | [Gregg: USE](https://www.brendangregg.com/usemethod.html), [TSA](https://www.brendangregg.com/tsamethod.html), [CPU flame graphs](https://www.brendangregg.com/FlameGraphs/cpuflamegraphs.html) | Question-led resource coverage; unknown metrics stay unknown; executing/runnable/wait distinctions; CPU samples explain busy CPU, not every elapsed-time cause. |

### Internal contradiction check and confidence

- **High:** local hotspots cannot establish cross-platform deltas; inclusive
  clocks overlap; medians are nonadditive; profiled elapsed is not official
  performance proof. These follow definitions and checked primary sources.
- **Medium:** the staged collection plan is likely sufficient to select a
  useful mechanism question; real log granularity, variance and tool coverage
  may require a narrower follow-up, not a large framework.
- **Low / unknown:** actual dominant differential, per-core/OS/toolchain shares,
  scanner ownership and prospective gains; no matched Mac profiles exist.
- The CPython unversioned page now describes newer profiling APIs; it was not
  substituted for the versioned cProfile contract. pyperf system tuning may
  change workload conditions/priority, so it is guidance, not a command plan.
  Apple's archived resource-unit wording must be checked against the actual
  runner's local API documentation before normalization. The original Amdahl
  ACM article was inaccessible (403); no claim to have read it is made.
