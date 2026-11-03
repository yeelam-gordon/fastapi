# Same-allocation runtime build control

One Windows ARM job, four-minute cap, original guardian with a 75-second cohort.
Exact CPython 3.13.15 stock/managed, one excluded warmup each, then AB and BA.
Only the interpreter argument changes in the default uv 0.13.6 sdist-to-wheel
build; PDM 2.5.0 is shared, hash-verified and offline. No project dependencies,
tests, backend changes, no-isolation, retries, or macOS job.

Existing source preparation, 2558-file raw manifest, phase clocks, native
attestation and full archive/RECORD equivalence are reused without modification.
Lexical executable paths are preserved. All six archives are checked.
Only strict natural-drain ownership receipts admit a completed result.
Local preflight may explicitly supply `--supplied-wheel` to `prepare`: this
requires the exact official wheel filename and SHA256 and an already-patched
canonical source snapshot. It performs no network request or automatic fallback.
Hosted preparation remains the original public PyPI path.
Advance requires >=5% and >=0.2s median savings, 2/2 favorable pairs, and all
quality gates. Otherwise close without retuning. No Windows/macOS parity claim.
