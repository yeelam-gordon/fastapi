# Verification evidence and unresolved execution

## Confirmed locally

- Native ARM64 CPython 3.13.15 and uv 0.13.6 execute; PDM 2.5.0 imports from the isolated environment.
- Benchmark stdlib tests: 11 passed, exit 0.
- Ruff 0.17.3 check and format checks: exit 0 for experiment Python.
- Two runs of seven alternating baseline/candidate trials each: command exit 0, offline after explicit preparation, pinned identical PDM version. Confirmation run records the harness bytes/SHA256 matching its committed source.
- Initial 16 retained artifact pairs revalidated independently with the final validator: matching normalized members/content, valid wheel `RECORD`, preserved sdist executable bits. Confirmation run's 16 additional builds also passed the same validator in the harness.
- Direct backend profiling: exit 0; resulting archives also match the timed baseline.
- PowerShell provisioning script parsing: zero parser errors.
- Native Windows ARM64 actionlint 1.7.12 validated the workflow: exit 0. This verifies workflow syntax/static rules, not runner execution.

## Independent review disposition

| Finding | Disposition | Evidence |
|---|---|---|
| B001: sdist comparison ignored executable permissions | Fixed by including executable bits in manifest fingerprints | Added regression fixture; independent revalidation of all artifacts, exit 0 |
| CI-001: unsorted imports failed repository Ruff rules | Fixed using native Ruff | Independent check/format exit 0 |
| CI-002: host architecture alone did not prove ARM64 Python | Fixed with `sysconfig.get_platform()` checks, including reused venv | Independent 24 architecture-case probes, exit 0 |
| VF-001: initial host/source/harness revisions were insufficiently distinguished | Corrected report provenance and performed a committed/fingerprinted confirmation run | Harness SHA256 matches committed bytes; source SHA explicit in report |
| VF-002: workboard retained obsolete hypothesis wording | Marked it as initial hypothesis and separated local proof from unproven CI benefit | Final findings/workboard use confirmed 23.8% local result |

Benchmark verifier returned **PASS/high** with report-median and trial-order assertions. CI reviewer returned **high** confidence in the concrete fixes but **medium** in overall readiness because no runner job, remote wheelhouse or installed-wheel smoke has executed. That distinction is retained rather than converted to a completion claim.

## Not verified

No Windows-versus-Mac timing comparison, physical-device comparison, end-to-end cold provisioning comparison, full FastAPI test suite or installed-wheel runtime smoke ran locally. CI execution was blocked at authenticated push by the missing OAuth workflow scope; local runtime dependencies were blocked by PyPI wheel TLS transport. The local benchmark result does not remove either limitation.
