# Pending fix verification

Status: **executed against committed producer fix
`3c10320c9ce03966a4d5f51cd8e8076a1095d235`; see FIX-REVIEW.md**.
The preparation instructions below are retained for reproduction.
The original findings and receipts in REPORT.md remain unchanged. No uncommitted
producer working files were read; verification used the authorized committed
fix cherry-picked without changes into this review branch.

After notification, export the candidate **from the supplied committed SHA**
into owned Q: scratch, record that SHA and file hashes, and put that exported
candidate first on `PYTHONPATH`. Do not test mutable producer working files.
Retain all new receipts under distinct `fixed-*` names.

## Required behavior

- `fixed_checks.py`: S1 then S3 on one source and unchanged manifest both succeed;
  payloads and complete archive permission fields remain equal.
- Stock isolated offline uv B then SDK succeeds on its one shared source, with
  canonical bytes and manifest unchanged. Child scratch/cache stay on owned Q:.
- Actual payload/version edits between SDK calls are reflected in the next
  complete sdist and wheel, with no manual build-state cleanup or manifest
  regeneration. This is a freshness check, not an immutable-source benchmark.
- Lowercase and mixed/uppercase hook aliases on this case-insensitive filesystem
  reject before output creation, and no harmless hook marker is written.
- `.pdm-build` directory symlinks and Windows junctions, at the root and nested
  within ordinary build state, plus uppercase root aliases, reject before output
  creation. External owned
  sentinel contents/membership and the link itself remain unchanged. Link
  creation failures are explicit skips, not passes or permission-policy changes.
- Preserve existing manifest/path/configuration rejection, writer/read errors,
  thread joins, optimized-Python checks and source-derived wheel guarantees.
  An unmanifested file in an unrelated dot-directory must still fail closed after
  an otherwise successful first build; broad hidden-directory skipping is not
  an acceptable state-reuse fix.
  Do not simply run all old `review_checks` tests: its three defect-reproduction
  tests deliberately expect the original failures.

`fixed_integration_check.py` repeats full canonical 79cab S1→S3 and B→SDK.
Every SDK artifact must match the immutable Mac oracle, including modes,
metadata and RECORD; the source manifest and every canonical input hash must
remain unchanged. B exit 0 does not waive its known Windows mode defect.
No Mac performance or parity inference is permitted.

## Execution after notification only

Use the existing official Python/PDM environment, `PYTHONDONTWRITEBYTECODE=1`,
the committed candidate export on `PYTHONPATH`, and this review directory as cwd.
Prepare a fresh owned copy of that candidate's verifier under
`scratch\candidate`, and run its `verify.py` against the read-only original
79cab checkout and local Mac oracle as described in REPORT.md. Then:

```powershell
& $python -B -m unittest -v test_candidate fixed_checks
& $python -B -O -m unittest -v test_candidate fixed_checks
& $python -B -m unittest -v review_checks.ReviewChecks.test_manifest_extra_missing_and_invalid_modes review_checks.ReviewChecks.test_plugins_and_configuration_rejected review_checks.ReviewChecks.test_wheel_only_reads_new_sdist review_checks.ReviewChecks.test_existing_and_nested_output_rejected review_checks.ReviewChecks.test_three_initial_reads_then_close_joins
& $python -B fixed_integration_check.py
```

Inspect the committed implementation independently before giving a final
disposition; prepared tests are not a substitute. Retain all exits/skips,
validate strict artifact receipts and rerun read-only Ruff. Necessary safety
walk/state cleanup remains inside whole CLI/wrapper timing. No timing loop,
C: performance experiment, CI, source-branch modification, or settings change
is authorized. The current preparation validates only test syntax/style, without
importing or executing candidate modules.
