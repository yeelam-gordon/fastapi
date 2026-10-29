# P24: activation files in temporary uv build environments

**Source lead only; no implementation or performance recommendation.** uv's
shared environment constructor writes activation templates even when called
for an isolated build. Whether avoiding those writes would save enough time
to justify a change is unknown. A generic ownership boundary is not evidence
of a worthwhile optimization.

## Pinned observations

The initial semantic search indexed a different commit and was used only to
locate symbols. All observations below were then checked against the exact
uv 0.13.6 revision `329bf9448afd9f9088d14a4d57fbc61eb454f117`, through read-only
GitHub raw-content API calls.

| Observation | Immutable source / symbol | Confidence |
|---|---|---|
| An isolated `SourceBuild` calls `uv_virtualenv::create_venv`; shared environments take a different branch | [uv-build-frontend/src/lib.rs](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs), `SourceBuild` setup, `build_isolation.shared_environment` | High |
| The temporary call selects no prompt, no system-site packages, temporary removal, non-relocatable behavior, disabled seeding and fixed upgrades | Same call site; these options are not an activation-file suppression switch | High |
| The public creation function forwards to the shared constructor without a separate activator option | [uv-virtualenv/src/lib.rs](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-virtualenv/src/lib.rs), `create_venv` | High |
| The constructor loops over `ACTIVATE_TEMPLATES`, substitutes paths and writes each selected script | [uv-virtualenv/src/virtualenv.rs](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-virtualenv/src/virtualenv.rs), template loop and `fs_err::write(scripts.join(name), activator)`; a relocatable-csh exception exists | High |
| Suppressing writes materially improves standard build latency | Not measured; no file/scan-count inference or Windows/Mac ratio | Low / unknown |

No source was modified, package installed, environment created, build timed,
protection changed, or CI run for this investigation.

## Maintainer gate

The appropriate owner would be uv, not FastAPI. A possible future question is
whether its internal temporary-build environment needs shell activation files,
without changing normal user-created environments, executable layout, installed
requirements, `PATH` or `VIRTUAL_ENV`. Backend expectations and compatibility
have not been established; the fact that uv runs hooks directly does not prove
every backend ignores activation files.

First establish a meaningful absolute cost under the real standard-command
lifecycle. Existing caller-readiness `S1.json` records about 0.433 s for an
entire separate `uv venv` invocation, including process startup and all other
creation work. This is one ordered historical smoke, not activator attribution,
not the frontend's in-process constructor cost and not a repeatable saving.
Do not double that number or subtract it from a stock build to predict benefit.

Only a demonstrated material cost would justify a small internal omission
policy and focused compatibility tests. A fresh uv source build, new settings,
or per-project script deletion is not justified now. A few saved writes with
negligible end-to-end benefit would fail the maintenance/review-cost gate.
Any eventual policy must be tested on Mac too, retaining its best applicable
configuration. No default change, upstream contact or PR is proposed.

Local historical reference:
`Generated Files\arm-build\protocol\wrapper-evidence\readiness-v2\S1.json`,
`phases[0]`; its old wrapper identities and bytecode-policy limits remain.
