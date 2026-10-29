# Prior work: evidence and attribution ledger

## Independent assessment, explicit credit

The supplied work is prior art, not a plan to copy or proof that a particular cause dominates this machine. Continue independent hypothesis selection, measurement and review. An exact match to an existing fix is credited to its original source; our contribution may be reproduction, verification, integration or a distinct improvement, not authorship of that fix.

Use these evidence labels separately: **user-reported**, **source-reviewed**, **locally reproduced**, **CI-reproduced**, and **not verifiable in the current environment**. Resolve mutable branch names to commit SHAs before drawing conclusions. Related mechanisms are not automatically identical fixes, and independent discovery does not erase prior-art credit.

## Supplied branches under audit

| Prior source | Claimed area | Current evidence boundary |
|---|---|---|
| [pip: windows-bytecode-threads](https://github.com/crutkas/pip/tree/review/windows-bytecode-threads) | Windows dependency/bytecode work | Source-reviewed at `d86a728f`; Windows-only threads, not cached bytecode; not reproduced |
| [Uvicorn: windows-graceful-reload](https://github.com/crutkas/uvicorn/tree/review/windows-graceful-reload) | Graceful reload | Source-reviewed at `58779399`; runtime, not package building |
| [Uvicorn: windows-reload-dedup](https://github.com/crutkas/uvicorn/tree/review/windows-reload-dedup) | Stacked reload fixes | Source-reviewed at `70ab5baf`; child of graceful fix, Windows WatchFiles path |
| [CPython: windows-ensurepip-hardlink-poc](https://github.com/crutkas/cpython/tree/review/windows-ensurepip-hardlink-poc) | ensurepip hardlink proof | Source-reviewed at `0e522c49` on Python 3.12 lineage; not a 3.13 drop-in or Windows-only gate |
| [HOBL: fastapi-real-world-benchmark](https://github.com/crutkas/HOBL/tree/crutkas-fastapi-real-world-benchmark) | Real-world benchmark and analysis | Source-reviewed at `5e9e1ae5`; maintainer and application metrics are distinct; supplied table not located |

Source receipts and reviews belong under `arm-build\prior-work`. No foreign patch has been installed into the system environment.

Reviews: [bootstrap](arm-build/prior-work/bootstrap/AUDIT.md), [Uvicorn](arm-build/prior-work/uvicorn/AUDIT.md), [HOBL](arm-build/prior-work/hobl/AUDIT.md). These are source-audit results, not measured speedup claims.

## Supplied results and estimate

The exact user-supplied numerical table and RICE estimate are retained in the ignored local file `arm-build\prior-work\private\USER-PROVIDED.md`. Their publication provenance is not established, so they are not included in public CI/repository evidence.

They are not our measurements. WSL is not macOS, and their timing boundary has not been established as equivalent to our distribution-package experiments. Verify commands, environments, raw samples and cache policy before ranking or combining numbers. The supplied RICE arithmetic is internally consistent, but its assumptions are not measured evidence established here.

## Relation to our existing experiments

Our recorded work so far concerns PDM packaging, source-byte normalization, archive materialization, tool imports and filesystem controls. Those experiments predate this supplied context, but no novelty claim is made. Existing pip/ensurepip/reload implementations must be credited if adopted or reproduced; ZIP-import or selective-extraction experiments are not automatically the same implementation merely because they also touch file I/O.

The live proposals remain in [INVESTIGATION-AND-PROPOSALS.md](INVESTIGATION-AND-PROPOSALS.md). Workload or scope changes require an explicit explanation rather than silently switching benchmarks.
