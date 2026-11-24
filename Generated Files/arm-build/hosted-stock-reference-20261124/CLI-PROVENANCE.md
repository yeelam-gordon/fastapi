# CLI qualification carried into the stock hosted comparison

The [prior successful hosted run](https://github.com/yeelam-gordon/fastapi/actions/runs/41972551771)
at `865da126b728d21d54980cc7729de7907828eec2` supports reuse of the CLI
audit, not reuse of its execution approval or its four ABBA timings.
The [independent audit](../pipe-matched-ci-readiness/ci-41972551771-independent-audit/independent-report.md)
checked both ARM64 platforms, all eight payloads, and their retained evidence.
That Mac ran `macos-14`; the stock comparison targets `macos-15`.

The pinned copies of `cli_identity.py`, `cli_coverage_identity.py`,
`cli_readiness.py`, `matched_policy.py`, `bootstrap.py`, and `full-coverage.toml`
are byte-identical to their blobs in the successful run. The stock driver's
`matched_audit.full` has the same Python AST as that run's `full` function.
The comparison used raw Git objects in source-only tree
`22cf1dfaaec909e970503aa0eb0f3685e49fc9b3`.

The new run must still verify the actual native interpreter, launcher and
CTracer on each host, then pass the existing per-payload Popen, wait, native
process-identity and raw-coverage association checks. None of those prospective
hosted checks, or any stock performance result, is claimed by this record.
