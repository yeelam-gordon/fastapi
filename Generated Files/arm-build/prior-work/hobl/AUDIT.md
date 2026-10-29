# HOBL workload audit

Pinned head: [`5e9e1ae540a8099485e30e2044ceb68d29d982e6`](https://github.com/crutkas/HOBL/commit/5e9e1ae540a8099485e30e2044ceb68d29d982e6). Source inspection only: no benchmark, installation, test or CI execution.

## Maintainer metrics are separate

| Metric | Timed command / boundary |
|---|---|
| `build_time` | Scenario Python `-m build`, including whatever isolated environment/backend preparation that frontend performs |
| `uv_build_time` | Scenario uv `build --out-dir ...`, a separate package build |
| `test_time` | Python `-m coverage run -m pytest tests`, full upstream tests |
| `scenario_runtime` | Sum of all three; not package creation alone |

Output removal is outside build timers. Outer scenario venv creation, test/dependency installation, installing the frontend and uv warm-up are also outside those phase timers. Isolation performed inside the measured frontend remains inside its timer. The frontend/backend are not completely pinned, so source alone cannot identify its historical ensurepip/virtualenv/external-pip call path.

The maintainer input is FastAPI 0.119.1 (`864b569cf8453654fc3bc2c64108c0f644e2918c`) and Python 3.12.10, with native ARM Python selected on Windows ARM. This is not our current FastAPI 0.162.0 / Python 3.13.15 setup.

Sources: [Windows timers, lines 342–419](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/scenarios/windows/fast_api/fast_api_resources/fast_api_run.ps1#L342-L419), [Mac timers, lines 40–90](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/scenarios/macos/mac_fast_api/mac_fast_api_resources/mac_fast_api_run.sh#L40-L90), [Windows preparation, lines 862–930](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/scenarios/windows/fast_api/fast_api_resources/fast_api_prep.ps1#L862-L930).

## Application metrics are different workloads

The shared application harness measures fresh-environment offline `uv sync`, dev-server readiness, fresh-process import/OpenAPI, tests, and optional reload separately. Its aggregate sums **startup, import/OpenAPI and test medians**, not sync/reload or the median of total-loop sums.

The app is `package=false`, pins FastAPI `[standard]==0.119.1`, and uses a lock. Sync follows cache preparation and excludes prior `.venv` deletion from its timer. Fresh import processes do not establish cold bytecode/filesystem caches; startup measurements precede imports.

Source: [shared harness, lines 111–124, 165–234, 389–444](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/scenarios/common/fast_api_app_workload/benchmark_inner_loop.py#L111-L124), [application configuration](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/scenarios/common/fast_api_app_workload/pyproject.toml#L1-L21).

## Published numbers versus missing evidence

The branch README publishes warm-cache Windows/WSL2 comparisons for uv sync, eager bytecode, offline venv/pip and diagnostic `--no-compile`. Those are verified as published claims, not independently reproduced measurements. They are **not** the separately supplied user table, retained locally until its publication provenance is established. No raw iterations, hardware manifests or exact “stock/final” revisions for that table were located.

Source: [published explanation, lines 35–60](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/scenarios/common/fast_api_app_workload/README.md#L35-L60).

Do not assign the supplied value to package build, setup or reload until its analysis/raw timer is supplied. WSL is not Mac; hardware and runtime architecture for those reported numbers remain unverified.

## Attribution and history

The upstream HOBL maintainer benchmark predates this branch. The prior branch contribution `a428df4efeeff36cadb00f8f95f90ef97cc12b6f` adds maintainer/app separation, app phases and modern uv metrics; later commits add bytecode discussion and diagnostic caveats. Those are prior contributions, not this audit.

The predecessor aggregate was legacy build plus tests; the new head adds uv build. The Mac test command also changes from `scripts/test.sh` to direct coverage pytest. Historical aggregate totals cannot be compared blindly across these revisions.

## Goal implication

Our distribution experiments overlap the package-build component only. They neither explain nor refute an unclassified reported number. For application setup/edit latency, package build alone is the wrong proxy. Keep legacy isolated build, modern build, setup, runtime and tests as separate contracts; request the missing analysis rather than silently changing the target.

Confidence: high on command boundaries and revision differences; medium on intended goal mapping; the supplied numerical table remains unverified.
