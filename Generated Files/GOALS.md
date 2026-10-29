# Goals: FastAPI build performance on Windows ARM

The project relationship, original circumstances, login-assistance rule and limited-CI-capacity gate are owned by [CIRCUMSTANCES.md](CIRCUMSTANCES.md).

## Ultimate outcomes

1. **GitHub CI:** Windows 11 ARM64 should build FastAPI at least as fast as macOS ARM64 under a comparable, verified workload.
2. **Physical hardware:** Evaluate and optimize the approximately 20-core Windows ARM machine against the approximately 16-core Mac, aiming for Windows to build faster. More cores alone are not proof.
3. **Next phase:** Extend the investigation to dependency setup and tests after establishing package-build performance.

These are targets, not already achieved results. Missing Mac access must not prevent source research, actionable proposals, local validation or preparation of the real CI comparison.

Continue the investigation/proposal/experiment loop until parity is established or a specific approval/access blocker requires user input. A partial speedup is not completion. The live ranked table is [INVESTIGATION-AND-PROPOSALS.md](INVESTIGATION-AND-PROPOSALS.md).

## Proposal ranking and adoption gate

Rank performance proposals in this order:

1. **Best: improve a common build toolchain.** Prefer maintainable changes in shared tools that benefit FastAPI and other similar projects without per-repository custom machinery.
2. **Good: demonstrate portable best practices in FastAPI.** Prefer supported tools, options and small configurations that other repositories can reasonably reuse. Credit existing capabilities rather than claiming them as new inventions.
3. **Reject: bespoke hacks or over-optimization.** Do not recommend non-scalable, FastAPI-specific machinery, private dependency monkey-patches or extra complexity whose technique cannot reasonably transfer to other projects. A faster prototype alone does not qualify.

**Maintainer acceptance is mandatory, not a fourth-place preference.** Before
recommending a change, identify the appropriate owner, explain the real problem
and measured value, show why the simplest supported alternative is insufficient,
and justify compatibility, code size, review burden and ongoing upkeep. A
maintainer should be able to understand why the change belongs in their project.
Do not open an upstream PR or claim owner agreement without authorization.
Any eventual owner-facing change must be a narrow patch in the appropriate
repository with focused tests and a short reproducible explanation. Do not
submit this research branch, generated evidence bundle or prototype framework
as a new requirement for FastAPI.

Keep diagnostic prototypes as evidence, not adoption recommendations. In
particular, the current FastAPI-specific SDK/private-PDM integration is
diagnostic-only; it must not be relabeled as a general toolchain improvement
without a credible owner-level implementation and validation across different
project layouts. Do not spend further CI capacity merely to optimize that
bespoke form.

## Acceptance principles

- Preserve FastAPI package contents and runtime behavior; do not omit work to win timings.
- Identify the actual build bottleneck and demonstrate improvements with repeated measurements and artifact verification.
- Compare explicit native ARM64 interpreters and documented hardware/software/cache conditions. Report build-only and setup-inclusive costs separately.
- Apply common optimizations to macOS where appropriate; track Windows/Mac ratios as well as absolute savings. Beating only an old Mac configuration does not establish parity.
- Prefer meaningful, maintainable improvements. Reject complexity whose measured value and compatibility assurance do not justify its review and upkeep.
- Run the Windows/macOS CI comparison when authorized. Never claim a prepared workflow is an executed comparison.
- State unmeasured outcomes, failures and blockers plainly.

## Required deliverables

Deliver measured, artifact-equivalent optimizations, a reproducible native toolchain, explicit ARM CI timing/architecture evidence and honest findings. Follow the storage, assistance and CI-budget constraints in [CIRCUMSTANCES.md](CIRCUMSTANCES.md).

The execution state is owned by [arm-build/WORKBOARD.md](arm-build/WORKBOARD.md); measured outcomes and limits are in [arm-build/FINDINGS.md](arm-build/FINDINGS.md).
