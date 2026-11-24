# Where does the extra pre-test time accrue in stock hosted HOBL?

The [stock run](ci-45310708354/RESULT.md) found 4.784–5.650 s of extra
Windows time before the first completed worker phase. The missing evidence
is whether the gap is already present at collection entry, accumulates
during collection, or appears before the first worker report after collection.
This run would diagnose that gap, not test an optimization.

Use the same Python, uv, package source, coverage, fixed dispatch and existing
storage as the stock run. One fork-only manual attempt, two jobs, 600 s per
job, 300 s queue acceptance, four stock A rows per job. Observation is
OFF/ON/ON/OFF, with no warmups, retries, or excluded rows. Do not dispatch
until the exact diagnostic workflow, receipts and offline verifier are bound.

All eight payloads must pass the stock integrity gates. OFF must have no
boundary sidecars; ON must have exactly the controller and every worker.
Each sidecar, receipt and mode record must match the final proof. Report
each worker's native test start to collection entry, collection entry to
collection-finish entry, and collection-finish entry to its first report
hook. Do not add concurrent worker durations or equate process CPU with wall.

For interpretation, keep the two adjacent ON/OFF test elapsed differences
per host. If any absolute difference exceeds 1.5 s or 5% of its OFF row,
report the observed intervals but do not use them to explain the stock gap:
the observer's effect could not be separated from run variation at that
resolution. Even if all differences are smaller, they are not a causal
overhead bound. Prioritize a specific stage only if the longest Windows
worker interval for that stage exceeds Mac's in both observed positions and
the same stage has the largest positive difference in both. Otherwise the
stage diagnosis is inconclusive. No parity or speedup claim follows.
