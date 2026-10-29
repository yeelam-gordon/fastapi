# Goals: FastAPI build performance on Windows ARM

The project relationship, original circumstances, login-assistance rule and limited-CI-capacity gate are owned by [CIRCUMSTANCES.md](CIRCUMSTANCES.md).

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

Deliver measured, artifact-equivalent optimizations, a reproducible native toolchain, explicit ARM CI timing/architecture evidence and honest findings. Follow the storage, assistance and CI-budget constraints in [CIRCUMSTANCES.md](CIRCUMSTANCES.md).

The execution state is owned by [arm-build/WORKBOARD.md](arm-build/WORKBOARD.md); measured outcomes and limits are in [arm-build/FINDINGS.md](arm-build/FINDINGS.md).
