# Circumstances and working constraints

## Original circumstances

1. Keep the persona, goals, research, actions, scripts and evidence under `Generated Files`. Only files that must be recognized elsewhere, such as an executable GitHub Actions workflow, belong outside it.
2. The starting machine is Windows ARM. Do not assume Python or performance tools are installed or executable: inspect, install what is missing and verify native execution.
3. There is no directly accessible Mac for local comparison. Prepare and run explicit Windows 11 ARM64/macOS ARM64 CI instrumentation when authorized. Missing hardware is not a reason to avoid research, proposals or validation that is possible.
4. Use subagents for substantial independent work and verification, following the user-supplied local `graph-routing.instructions.md`.

## Added circumstances

### Independent investigation, not upstream project work

No FastAPI contributor or maintainer authority is assumed. Keep experimental changes local or in the owned fork. Opening an upstream pull request requires an explicit user request.

### Required human assistance

When a command or login requires the user's help, display a dialog with the exact required action and continue independent useful work in parallel. Do not ask for tokens in chat or store authorization/device codes in research files. Avoid duplicate login prompts after authorization is confirmed.

### Limited fork CI capacity

The fork's CI capacity is limited, not infinite. This does not prohibit useful runs. Before each dispatch:

- Define the specific unanswered question.
- Pass relevant local tests, static checks and available provisioning/build smoke checks.
- Identify uncertainties that can only be checked on the actual runner.
- Inspect the previous run's evidence and explain why another run is warranted.

Do not retry automatically or use CI as a substitute for available local validation.

### Protected Windows filesystem and repeated scanning

The user reports that the Windows ARM CI machine does **not** use Dev Drive. The local Q: drive is reported as Dev Drive and may hide benefits from reducing scan-sensitive filesystem work; evaluate those optimizations on C: as well.

The target is fewer unnecessary source copies, extracted files, intermediate writes, reopen/rewrite passes and repeated scans—not weaker endpoint protection. Do not disable Defender/MDE, add exclusions, change tamper/UAC settings or change drive trust. Attribute a speed difference to antivirus only with scan evidence, not merely a C:/Q: timing difference.

### Shared gains and over-optimization

An optimization that helps macOS too can be useful, but a Windows absolute speedup does not establish progress toward relative parity. Evaluate applicable common optimizations on both platforms and track the Windows/Mac ratio separately.

Show maintenance cost and compatibility risk alongside timing gains. Do not recommend a complex custom packager or new toolchain for a small benefit; the user may reject over-optimization.

### Supplied prior work and independent reasoning

Prior optimization branches and reported benchmark results are inputs for independent research, not authority to replace our diagnosis. Some results may not be reproducible in this environment. If a proposal exactly matches existing work, credit that prior source and do not claim authorship. [PRIOR-WORK.md](PRIOR-WORK.md) owns the source and attribution ledger.

### Per-investigation isolation and coordination capacity

Delegate substantial investigations and proposal evaluations to subagents, with a separate Git branch/worktree for each active lane. Keep measured source inputs separate and immutable; do not move files during a timed experiment. The master owns integration, acceptance and the shared workboard.

Use 2-3 active lanes as the normal minimum when independent work is ready, and no more than 15 subagents. Do not serialize independent research unnecessarily. Disk-intensive timed workloads sharing a device may require serialization while source research, implementation or review continues in parallel.

If coordination capacity becomes the bottleneck, prepare a bounded handoff in a new `Generated Files` subfolder and show the user a dialog requesting another full agent. Do not silently expand into an unbounded worker fleet. Completed pre-isolation experiments remain historical evidence; new iterations use the isolated lanes.

### Competing performance hypotheses

Do not assume Defender is the sole cause. Research interpreter/toolchain optimization quality, compiler/build configuration, filesystem/storage behavior, dependency implementation and wheel availability, ARM-native execution/ISA acceleration, and the actual timed workload. Rank them using measured stage costs and verified source facts; do not rebuild toolchains or add complexity merely because a hypothesis sounds plausible.

## Observed environment, not assumptions

The current host is a **16-core Cobalt 100 Windows ARM64 VM**, not the eventual approximately 20-core physical machine. Read-only inspection confirms Q: is ReFS and C: is NTFS; privileged Dev Drive status queries were denied, so effective local trust/performance-mode status is not independently established. CPython 3.13.15 was already installed and works natively. The PATH uv executable was broken; a verified native copy was installed for the experiment. PyPI binary TLS transport failed locally; official GitHub source bootstrap and the successful Windows CI wheelhouse provide recovery paths.

GitHub initially rejected workflow pushes without the `workflow` OAuth scope. The user completed authorization; that blocker is resolved. No further login is needed.

These are environment observations, not evidence that Windows is faster or slower than macOS.

## Current experiment disposition

The first CI run, [40814042898](https://github.com/yeelam-gordon/fastapi/actions/runs/40814042898), failed **overall**. Its Windows ARM job passed package measurements and installed-wheel smoke. Its macOS job failed before provisioning because the experiment incorrectly rejected a native `universal2` Python build tag.

The corrected guard has ARM-versus-Rosetta regression coverage. A separately validated managed-Python provisioning path replaces the slow Windows installer setup. The second run, [40814588064](https://github.com/yeelam-gordon/fastapi/actions/runs/40814588064), **passed both ARM jobs**, including installed-wheel smoke. Strict postprocessing still rejected package newline/executable-mode differences. The newline correction was validated locally; executable-mode differences remain explicit. Successful CI does not establish parity, and no further run is scheduled.

[PERSONA.md](PERSONA.md) owns the expert method; [GOALS.md](GOALS.md) owns the targets. [arm-build/WORKBOARD.md](arm-build/WORKBOARD.md) owns live execution state, and [arm-build/CI.md](arm-build/CI.md) owns detailed CI evidence and reproduction.
