# Goals: FastAPI build performance on Windows ARM

## Project relationship and authority

This is an independent performance investigation, not an upstream FastAPI initiative. No contributor or maintainer authority is assumed. Keep experimental changes local or on the owned fork; opening an upstream pull request requires an explicit user request.

## Ultimate outcomes

1. **GitHub CI:** Windows 11 ARM64 should build FastAPI at least as fast as macOS ARM64 under a comparable, verified workload.
2. **Physical hardware:** Evaluate and optimize the approximately 20-core Windows ARM machine against the approximately 16-core Mac, aiming for Windows to build faster. More cores alone are not proof.
3. **Next phase:** Extend the investigation to dependency setup and tests after establishing package-build performance.

These are targets, not already achieved results. Missing Mac access must not prevent source research, actionable proposals, local validation or preparation of the real CI comparison.

## Acceptance principles

- Preserve FastAPI package contents and runtime behavior; do not omit work to win timings.
- Identify the actual build bottleneck and demonstrate improvements with repeated measurements and artifact verification.
- Compare explicit native ARM64 interpreters and documented hardware/software/cache conditions. Report build-only and setup-inclusive costs separately.
- Run the Windows/macOS CI comparison when authorized. Never claim a prepared workflow is an executed comparison.
- State unmeasured outcomes, failures and blockers plainly.

## Required deliverables

- Keep persona, goals, research, actions, scripts and evidence under `Generated Files`.
- Install missing native Python/build/profiling tools as needed; verify existing installations before replacing them.
- Prepare extra CI timing, architecture and artifact evidence on explicit ARM runners. The executable workflow necessarily lives in `.github\workflows`; its research and evidence belong here.
- Use independent subagents for substantial parallel work and verification, following the supplied graph-routing instructions.
- Request required login or command assistance through a dialog while continuing independent useful work.

The execution state is owned by [arm-build/WORKBOARD.md](arm-build/WORKBOARD.md); measured outcomes and limits are in [arm-build/FINDINGS.md](arm-build/FINDINGS.md).
