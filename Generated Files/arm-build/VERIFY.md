# Verification evidence and unresolved execution

## Confirmed locally

- Native ARM64 CPython 3.13.15 and uv 0.13.6 execute; PDM 2.5.0 imports from the isolated environment.
- Benchmark stdlib tests: 12 passed after the native Mac `universal2` regression fix, exit 0. Comparison tests: 14 passed after raw-hash/CRLF handling, exit 0.
- Ruff 0.17.3 check and format checks: exit 0 for experiment Python.
- Two runs of seven alternating baseline/candidate trials each: command exit 0, offline after explicit preparation, pinned identical PDM version. Confirmation run records the harness bytes/SHA256 matching its committed source.
- Initial 16 retained artifact pairs revalidated independently with the final validator: matching normalized members/content, valid wheel `RECORD`, preserved sdist executable bits. Confirmation run's 16 additional builds also passed the same validator in the harness.
- Direct backend profiling: exit 0; resulting archives also match the timed baseline.
- PowerShell provisioning script parsing: zero parser errors.
- Native Windows ARM64 actionlint 1.7.12 validated the workflow: exit 0. Corrected CI subsequently passed both real ARM jobs and installed-wheel smoke checks.
- Official native build/profiling/minimal-runtime dependencies were restored offline from the successful Windows wheelhouse. `pip check` and installed-FastAPI smoke passed locally; full repository tests were not run.
- Local canonical-source correction passed a five-pair benchmark and matches every retained Mac reference wheel/sdist member's contents. Five sdist executable-mode differences remain, and strict cross-platform equivalence is not asserted.

## Independent review disposition

| Finding | Disposition | Evidence |
|---|---|---|
| B001: sdist comparison ignored executable permissions | Fixed by including executable bits in manifest fingerprints | Added regression fixture; independent revalidation of all artifacts, exit 0 |
| CI-001: unsorted imports failed repository Ruff rules | Fixed using native Ruff | Independent check/format exit 0 |
| CI-002: host architecture alone did not prove ARM64 Python | Fixed with `sysconfig.get_platform()` checks, including reused venv | Independent 24 architecture-case probes, exit 0 |
| VF-001: initial host/source/harness revisions were insufficiently distinguished | Corrected report provenance and performed a committed/fingerprinted confirmation run | Harness SHA256 matches committed bytes; source SHA explicit in report |
| VF-002: workboard retained obsolete hypothesis wording | Marked it as initial hypothesis and separated local proof from unproven CI benefit | Final findings/workboard use confirmed 23.8% local result |

Initial benchmark review returned **PASS/high** with median/order assertions. Initial CI readiness was medium while unrun; real execution then exposed the missing native `universal2` case, which was fixed with regression coverage. The corrected run passed both jobs. The comparison worker returned **high** confidence in its strict rejection diagnostics; no content or executable-mode mismatch was waived to manufacture a performance win.

Root revalidated all 32 initial local artifact pairs, source-diff identity and the committed-harness fingerprint with exit 0; that execution is labeled root-owned, not misattributed to the read-only auditor. [Receipt](results/environment/final-validation.json).

## Final independent execution

A fresh full-tool verifier returned **high confidence in the evidence**, not a parity claim. It executed all 26 benchmark/comparison tests and actionlint (exit 0), independently reproduced the source fingerprints and reported arithmetic, checked all 12 canonical local artifact pairs against the Mac reference, and confirmed the remaining five executable-mode differences were not waived. It also checked that no package/runtime/production manifest changed. A minor workboard wording issue was corrected to distinguish measured CI build-only improvement from unestablished end-to-end benefit.

## Remaining limits

The recorded Windows/Mac medians are observations, not an accepted artifact-identical comparison. Original CI inputs differed in newline bytes, and source canonicalization has only been rerun locally. Five sdist script executable-mode differences remain unresolved. Physical-device parity, stable cross-job statistical parity, setup-inclusive single-build latency and the full FastAPI test suite remain unverified. Only two CI runs were used; no third run is scheduled.
