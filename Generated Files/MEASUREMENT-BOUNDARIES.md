# What the timing labels mean

## Repository preparation is not package building

The GitHub `actions/checkout` step includes fetching source, creating working
files and setting up/removing Git credentials. Its elapsed time is not the
duration of only the `git checkout` command.

Both historical ARM jobs used `fetch-depth: 1` and fetched with `--depth=1`.
They were already shallow checkouts, not downloads of full history.
Observed checkout-associated intervals do not establish an MDE cause.

In the earlier audit, **window meant a time interval**, not the Windows
operating system or a graphical window. Both runners executed the same six
Git credential setup/cleanup `git submodule foreach` commands. Their logged
interval totals differed. These are not FastAPI application authentication
operations. Prefer the label **Git credential setup/cleanup intervals**.

## Package creation can be short

FastAPI's distribution is pure Python: package building creates a source
archive and wheel rather than compiling the application into a native program.
The stock package-only commands measured here take seconds. Dependency setup,
repository preparation, tests, application startup and release publishing are
different boundaries; do not silently include or exclude them.

## A dashboard row needs its own definition

A displayed project name and elapsed duration do not identify the timed command.
In the pinned HOBL revision audited under `arm-build\prior-work\hobl`, separate
metrics are:

| Metric | Boundary |
|---|---|
| `build_time` | `python -m build`, including its internal isolation |
| `uv_build_time` | A separate `uv build` package operation |
| `test_time` | Coverage plus the upstream pytest suite |
| `scenario_runtime` | Sum of all three, not just package creation |

That revision uses different FastAPI/Python versions from our current package
experiment, and earlier HOBL revisions had different aggregates. A user-shared
screenshot has not yet been mapped to an exact timer/revision. Do not assign
its duration to one of these metrics without provenance, or claim a package-only
speedup solved a broader row.

The original build-first goal is retained. Before spending the next CI
allocation, establish whether its package component is the intended target
or whether the dashboard's broader workload must be reproduced. The user
clarification dialog was unavailable; public metric-definition tracing can
continue without spending CI or publishing unclassified supplied values.
