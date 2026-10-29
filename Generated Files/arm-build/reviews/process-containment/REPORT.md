# Independent bounded containment review

Reviewed `935b9bedcad2f876901b17e3d2a93dc0553adbde`, specifically the
305-line `protocol/owned_process.py`, its nine tests, the implementation
contract, and the original PP003 adjudication. Source SHA256:
`24ba19d699e3815a8ae8692d89288b7d4fbe183bf5d33469f8ffca6993a244cc`.
No producer changes, builds, benchmarks, CI, pushes, or nested delegation.

## Disposition

**Core local Windows containment and timer design pass; one low-severity
cleanup/error-contract defect remains.** This is not integrated PP003 closure.
Confidence is **high** for the exercised native Windows ARM64 paths and the
finding, **medium** for source/mocked POSIX behavior, and **low** for unexecuted
macOS/hosted-runner runtime compatibility.

### PC001 — cleanup exceptions can discard the original failure and stop cleanup

Low severity; high confidence. At `owned_process.py:108–110`, failure while
closing a newly created job replaces the original setup exception in the
receipt's serialized error (Python exception context is not serialized).
At `owned_process.py:287–289`, stream closes are unchecked and sequential.
An exception from the first close escapes `run_owned` instead of returning
the promised Receipt, discards the original command's returncode from the
caller-visible result, and skips the remaining pipe closes.

`verify.py` reproduces both with injected failures: setup+close produces only
the secondary error; stdin close failure after command returncode 7 raises
and never attempts stdout/stderr close. These are failure-injection proofs,
not observed native handle-close failures. They do not demonstrate false
success or a live-process escape; hence low severity rather than a blocker
against the demonstrated containment mechanism.

Concrete bounded correction: retain setup and secondary close diagnostics;
attempt every pipe close independently, append errors and mark cleanup
incomplete, then return the original returncode/error in Receipt. This needs
only local try/except handling, not a new resource-management framework.

## Verified behavior

- Parent creates and retains the named KILL_ON_JOB_CLOSE job; supervisor
  assigns itself before target spawn and closes its own noninherited handle.
  Membership propagates through ordinary children without ancestry polling.
  Real independent proof terminates only the known controller PID and
  observes its recorded supervisor, target, and grandchild all terminate.
  Finally blocks immediately terminate/check only those known PIDs.
- Existing real tests reject a successful fast root with an exited intermediate
  and live grandchild; clean the family; cover timeout, normal/nonzero exits,
  raw logs, and failed setup/query/drain. Independent missing-executable proof
  retains FileNotFoundError, rejects success, and verifies cleanup.
- `Receipt.succeeded` requires established ownership, no survivors, completed
  cleanup, no timeout/errors, and returncode zero. Missing/unknown ownership,
  surviving family, and timeout do not become success after cleanup.
- Native interpreter: `C:\Program Files\Python313-arm64\python.exe`,
  ARM64, 64-bit. Actual Windows HANDLE restypes are pointer-width `c_void_p`;
  DWORD is Windows 32-bit, sizes/affinity use pointer-width types. Live
  SetInformationJobObject and empty-job query succeeded. Captured layouts:
  BASIC_LIMIT_INFORMATION 64 bytes, EXTENDED_LIMIT_INFORMATION 144 bytes;
  basic field offsets 0,8,16,24,32,40,48,56,60, matching native alignment.
  No guessed byte offsets, private process inspection, NtResumeProcess,
  name kills, or environment/credential persistence.
- Timer starts immediately before target Popen, not supervisor launch.
  Ends after supervisor completion, family checking/drain and handle cleanup.
  Deterministic independent tests exercise both platform branches: outer
  start 100, target start 103, end 112 gives infrastructure 3 and command 9,
  including cleanup. Log opening/setup is infrastructure on both OSes;
  target argv/package work is inside the command boundary. No performance
  measurement was made or supervisor overhead represented as backend time.

## Portability and scope gates

POSIX uses a new supervisor session/group and public group signaling. The
fixed family must inherit that group and never deliberately detach.
The wrapper's known per-phase `start_new_session=True` prerequisite is already
documented and being fixed elsewhere; it is **not a new finding** here.
POSIX unit mocks/source inspection are not macOS execution certification.
The implementation expressly does **not** promise POSIX parent-crash cleanup;
Windows parent-death proof must not be generalized to that platform. If the
root requires parent-crash containment on both OSes, that exceeds this
documented POSIX guarantee and remains an explicit acceptance decision.

Hosted Windows inherited/nested-job restrictions remain a runtime gate.
The job-only documented PID query is proportionate: it obtains termination
wait handles without system-wide/private process enumeration. Known-PID
waits plus accounting/drain checks improve on accounting alone; this proof
does not certify every possible process-creation/termination interleaving.

305 lines include typed ctypes signatures, SDK structures, receipt,
supervisor, and both cleanup paths. There is no concrete equivalent
180-line implementation established by this review that preserves these
checks; line count alone is not an architecture finding. No framework,
watcher threads, new dependencies, or machine policy changes were introduced.

Before future CI use, freeze/hash the **then-current supervisor bytes**
alongside the other required inputs; this hash covers only the reviewed
revision. Harness receipt integration and stop-after-failure behavior belong
to the other lane and were not certified here.

## Executed evidence

From this worktree using native Python:

- `python "Generated Files\arm-build\protocol\test_owned_process.py"`:
  9 passed, 4.469s.
- Same with `python -O`: 9 passed, 4.500s.
- `python "Generated Files\arm-build\reviews\process-containment\verify.py"`:
  5 passed, 1.219s; same with `python -O`: 5 passed, 1.190s.
- `git diff --check`: passed.

All real helpers use project-local unique directories and explicit PID
receipts; those directories are removed. No dependency installations or
environment capture. Report and small repros are the only owned changes.
