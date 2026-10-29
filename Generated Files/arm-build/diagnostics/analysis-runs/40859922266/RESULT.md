# Analysis allocation 40859922266: incomplete paired collection

Code: `675fd789e686c2fbd068c2e921e8a7b76d4dfeda`.
One allocation, two ARM jobs; no retries or performance-improvement run.

- Windows retained normal context and resource/function/import/allocation
  artifacts. All eight build receipts returned zero without timeout.
  Strict artifact/source-mode differences remain explicit, not waived.
- Mac stopped at contract tests before any build profiling. Two bugs in our
  test fixtures, not a FastAPI build, caused the stop: global platform mocking
  corrupted lazy sysconfig selection, and a raw-path assertion ignored HOME
  redaction. Source repair `1d23307d1` reproduces and fixes both locally.
  Native Mac collection after that repair remains unexecuted.
- Windows total job time and Mac's early-failed job time are not a build-speed
  comparison. Mac hook metrics and Windows-minus-Mac hook gaps are unavailable.
- Safe artifacts and full final metadata/console are retained. The collector's
  Windows failure signal is not silently made green. Native capture is not
  established.

Actual Actions Node receipts on both jobs report ARM64 Node v24.21.0.
Windows identifies Cobalt 100 / four allocated CPUs; Mac identifies
Apple M1 (Virtual) / three. These are different platform stacks.

The next proposal is a single Mac-only backfill, preserving the existing Windows
data and recording the test-only/code-workflow differences. It needs a separately
approved allocation; the approval dialog was unavailable. No further CI is
authorized automatically. No matched mechanism or parity claim is supported.
