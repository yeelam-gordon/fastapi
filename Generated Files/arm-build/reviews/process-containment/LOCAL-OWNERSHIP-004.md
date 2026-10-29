# LOCAL-OWNERSHIP-004: independent diagnostic, fix review held

**Disposition: retain the integration blocker. Cause remains unestablished.**
The supplied frozen preflight and raw normal-suite log show a real rejected
normal receipt: returncode 0, no timeout/errors, ownership established,
survivors true, cleanup complete. This is not a successful receipt and must
not be reclassified as one because later diagnostics pass.

Reviewed evidence is the supplied `local-paired-readiness` worktree's
`readiness-local\frozen-preflight.json` and
`frozen-normal-test_owned_process.py.log`, frozen revision
`102ddabcb3a03b33915cb11534925c0951c2df72`.
No producer changes, C: writes, builds, parent-death repeats, benchmarks,
performance samples, CI, or machine/security changes were performed.
Final fix review is held pending the root-supplied producer commit.

## Exact runtime and byte identity

The diagnostic controller used the requested interpreter read-only:
`C:\fastapi-arm-build-lab\paired-v4-2a73e36a\f87c928ba5ad409087d1695f0995067e\env\Scripts\python.exe`.
It reports CPython 3.13.15, native ARM64; base prefix is
`C:\Users\yeelam\AppData\Roaming\uv\python\cpython-3.13-windows-aarch64-none`.

The review worktree's producer bytes match the frozen receipt:

- owned_process.py SHA256:
  `9db21a2aab063a424b135588324835947f3d69a2e0d96ab422783d6b4bef9666`.
- test_owned_process.py SHA256:
  `9298d36c382a3cf09d4417491087891dc9dd874bbdbafd16f8a06a70fbaf017b`.

These are not necessarily the same executable/cwd/path conditions as the
original C:-resident suite. This diagnostic intentionally uses Q: scratch;
it does not modify or replace the frozen integration result.

## Bounded observations

`diagnose004.py` invokes the existing exact normal test method and its helper
through a subclass that records the returned receipt before normal teardown.
`diagnose004.json` retains **8 uninstrumented + 8 instrumented** repetitions.
All 16 returncode-zero receipts have survivors false, cleanup true, no errors;
all 16 original normal-test assertions pass. Six preliminary instrumented
normal calls also passed before the recorded split was introduced; their
console output is not part of the final JSON. No further repetitions planned.

Instrumentation wraps only parent-side supervisor Popen and job accounting.
It captures the supervisor's known launch PID and public process image.
Only if the original accounting query reports alive does it additionally
query the documented owned-job PID list and known-PID image/wait state.
The first accounting check was false in every recorded instrumented call,
so **there is no captured survivor PID for the failing condition**.
Instrumentation timing can affect observations; the eight uninstrumented
calls avoid that added query overhead but cannot establish failure frequency.

One separate minimal normal target records PID/parent/executable, not a
replacement for the failing test:

- Controller is the requested venv Python.
- `run_owned` launches base-prefix Python, not env\Scripts Python, for the
  supervisor. Public QueryFullProcessImageName resolves its actual image to
  the versioned uv Python installation.
- Popen supervisor PID was **2888**; target PID **23044** reports parent
  **2888**, and target sys.executable is also base-prefix Python.
  Thus this observed supervisor was the target's direct parent; no extra
  venv launcher between those two PIDs is demonstrated in this probe.
- Receipt establishes job ownership and reports no survivors. Source places
  the supervisor in the job before target creation, closes its own job
  handle, and inherits membership into the target. No live job membership
  snapshot from the original failure is available.

All process inspection is public and limited to explicit launch/owned-job
PIDs, not a system process census or private process details. Helper scratch
directories were removed by the existing tests/separate probe cleanup.

## What this does and does not establish

High confidence in the supplied actual integration failure and the recorded
non-reproduction outcomes. The frozen receipt alone proves that the helper's
first survivor check was true and later cleanup succeeded; it does not identify
which job member was counted, whether it was still executing, or why.
Returncode zero and empty errors do not answer those questions.

**No evidence-backed root cause was captured.** Do not label this a transient
race, accounting lag, or venv-launcher artifact on these observations alone.
The direct-parent probe only constrains one successful execution; it cannot
exclude a different lifetime relationship in the failing execution.
Do not silently add an arbitrary grace delay or accept/retry the frozen
failure on the strength of these passing diagnostic repetitions.

The next bounded producer evidence should identify the owned member(s) and
their documented process-handle state at the actual first-positive accounting
check, while retaining the original receipt and all cleanup checks. Review
the root-supplied fix against those observations before claiming closure.

No macOS execution occurred. POSIX evidence remains prior source/unit mocks;
confidence in macOS runtime behavior remains low. No Windows result is
extended to Mac ownership or parent-crash cleanup.
