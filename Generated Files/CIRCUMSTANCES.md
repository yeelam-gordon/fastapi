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

## Observed environment, not assumptions

The current host is a **16-core Cobalt 100 Windows ARM64 VM**, not the eventual approximately 20-core physical machine. CPython 3.13.15 was already installed and works natively. The PATH uv executable was broken; a verified native copy was installed for the experiment. PyPI binary TLS transport failed locally; official GitHub source bootstrap and the successful Windows CI wheelhouse provide recovery paths.

GitHub initially rejected workflow pushes without the `workflow` OAuth scope. The user completed authorization; that blocker is resolved. No further login is needed.

These are environment observations, not evidence that Windows is faster or slower than macOS.

## Current experiment disposition

The first CI run, [40814042898](https://github.com/yeelam-gordon/fastapi/actions/runs/40814042898), failed **overall**. Its Windows ARM job passed package measurements and installed-wheel smoke. Its macOS job failed before provisioning because the experiment incorrectly rejected a native `universal2` Python build tag.

The corrected guard has ARM-versus-Rosetta regression coverage. A separately validated managed-Python provisioning path replaces the slow Windows installer setup. The second run, [40814588064](https://github.com/yeelam-gordon/fastapi/actions/runs/40814588064), **passed both ARM jobs**, including installed-wheel smoke. Strict postprocessing still rejected package newline/executable-mode differences. The newline correction was validated locally; executable-mode differences remain explicit. Successful CI does not establish parity, and no further run is scheduled.

[PERSONA.md](PERSONA.md) owns the expert method; [GOALS.md](GOALS.md) owns the targets. [arm-build/WORKBOARD.md](arm-build/WORKBOARD.md) owns live execution state, and [arm-build/CI.md](arm-build/CI.md) owns detailed CI evidence and reproduction.
