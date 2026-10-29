# Independent review: committed membership/wait-state correction

Producer `e76535100babcca92c3492516e9f2328b56b6303` cherry-picked with
attribution as `86438fc63d9938642902fcba5cd3d32d763f3cf6`.
Reviewed only committed producer changes; no producer hand edits.
Supervisor SHA256:
`1117af6abd926a23961e5c51fcf444dc96e4b852f709c663c169b4166bc6a57a`.

**Disposition:** the positive-accounting correction is principled and
proportionate; no demonstrated false-success race in its two-snapshot
observation path. One low-severity cleanup defect remains (PC002 below).
The original LOCAL-OWNERSHIP-004 failed receipt remains valid historical
evidence; its cause is still unestablished. Passing revised tests are not
a causal explanation or authorization for the frozen campaign.

## Independent acceptance matrix

| Contract/countercase | Required outcome | Evidence |
|---|---|---|
| Buffer insufficient / concurrent growth / partial success | Retry with bounded growth; never accept partial list | Independent mock: failed 8-slot query, successful but partial 16-slot query, complete 32-slot query containing 17 PIDs |
| Enumeration access error / never-completing growth | Unknown failure, not empty | Independent API-return/error and capacity-bound tests |
| Supervisor exclusion | Exclude only already-waited supervisor launch PID | Independent `{10,20,30}` test opens 20/30; source retains Popen object through cleanup |
| Signaled owned member | Terminated, not executing survivor | Producer test; independent signaled-handle checks |
| Nonsignaled owned member | Survivor remains true even if cleanup later works | Independent WAIT_TIMEOUT; real producer orphan/grandchild and timeout tests |
| PID already absent | Accept absence only after complete second snapshot | Independent ERROR_INVALID_PARAMETER: absent passes; same/new PID in second snapshot rejects |
| PID reused outside job | Unknown identity failure, not ignored/departed | Independent IsProcessInJob false; no unrelated process termination |
| Membership query fails / wait fails / process access denied | Unknown, exception/fail-closed | Independent false API returns, exceptions, WAIT_FAILED, second-query failure |
| New member between snapshots | Reject changed membership, no retry-to-success waiver | Independent `{20,30}` then `{20,30,40}` |
| Process identity pinning | Hold every acquired handle through second snapshot | Independent second-snapshot assertion that no CloseHandle occurred |
| Observation handle close fails, including primary error | Attempt every close; record secondary errors; preserve primary | Independent two-handle failure injections pass |
| Termination-path handle close fails | Same all-close/original-error requirement | **PC002 fails**, independently reproduced below |
| Accounting zero | Existing shortcut skips membership observations | Independent integration mock confirms; documented zero count contract discussed below |

`test_membership_review.py` contains nine test methods with the matrix
subcases. Counterexample tests deliberately assert the observed unresolved
behavior, not a fictional fix.

## PC002 — termination cleanup still skips remaining handles

**Low severity, high confidence.** `_Job.kill`'s finally block still executes
unchecked sequential `_checked(CloseHandle(handle))` calls. Inject a primary
TerminateJobObject failure after obtaining two synchronization handles, then
fail the first CloseHandle: the secondary close error replaces the original
termination error, and the second handle close is never attempted.

The independent test confirms two opens but only one close. No native handle
failure or escaped real process is claimed. `run_owned` still fails closed
and closes the job as fallback; this is not false sample acceptance.
It nevertheless violates the requested all-handles-clean/original-error
contract on this tightly related termination path. This loop predates the
new correction; the new live_members finally block already handles its
analogous case correctly. Apply that bounded local discipline here too:
attempt every close and retain primary plus secondary diagnostics. No new
framework is needed. This is the remaining implementation acceptance item.

## Race argument and documented API boundaries

The member list includes nested-job descendants. Compare returned and
assigned counts; ERROR_MORE_DATA or partial success cannot establish complete
membership. OpenProcess uses SYNCHRONIZE plus QUERY_LIMITED_INFORMATION,
and IsProcessInJob validates the exact opened object against the owned job.
WAIT_OBJECT_0 means signaled termination; WAIT_TIMEOUT means nonsignaled.
WAIT_FAILED and other unexpected states are never interpreted as termination.

For the positive-accounting path, retaining opened handles across the second
complete snapshot prevents replacing a checked object with a new object via
PID recycling while it is being validated. A departed ID must disappear;
any new ID rejects. With the known supervisor already waited and all
remaining objects signaled/absent, the supported fixed family has no observed
executing member left to spawn another descendant. This argument assumes no
external actor assigning fresh unrelated processes to the private random job,
and the existing no-breakaway/inherited-membership contract. It is not a
proof for hostile services, arbitrary external process creation, or macOS.

The implementation still uses `job.alive() and job.live_members(...)`.
Accounting zero therefore returns without a PID-list query. The independent
mock makes that shortcut explicit, but **does not demonstrate a native
false-success bug**: the public ActiveProcesses contract is the number of
processes currently associated, decremented after the terminated process exits
and references release. A mock simultaneously asserting zero association and
an executing associated member is not evidence that Win32 permits that state.
The change is not an unconditional membership query on every path; retain
this boundary in documentation/claims rather than overstating coverage.

The added logic is local typed API validation, a reused enumeration helper,
bounded second snapshot and additive receipt evidence. It introduces no sleep,
waiver, watcher, new dependency or general framework. Target/setup timer
boundaries remain unchanged; validation cost stays charged to command cleanup.

## Executed proof and confidence

Using only the supplied managed native ARM64 interpreter, read-only, with
Q: worktree paths and scratch:

- Producer `test_owned_process.py`: **14 passed normally (4.191s)**;
  **14 passed with -O (4.159s)**.
- Independent `test_membership_review.py`: **9 passed normally (0.009s)**;
  **9 passed with -O (0.009s)**. These include historical PC002 counterevidence.
- `git diff --check`: passed.

No repeated non-reproducing diagnostic normal loop or parent-death experiment,
no C: writes, builds, performance samples, benchmark or CI. The producer's
reported new parent-death runs were not independently repeated here.
All independent negative tests use mocks: they create no processes/OS handles.
The producer suite supplies real normal/orphan/timeout evidence.

Confidence **high** in the demonstrated tests and PC002; **medium** in the
bounded membership/race argument and hosted Windows compatibility; **low** in
unexecuted macOS runtime. Remaining integration gates are original-failure
disposition, exact input freezing including this changed helper hash, full
receipt/liveness serialization and abort behavior, hosted nested-job support,
and the already-known POSIX wrapper inheritance prerequisite. No Mac
parent-crash guarantee or cross-OS certification is inferred.

## Public contracts checked

- [Owned PID list and count completeness](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list)
- [Job query errors/access](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject)
- [IsProcessInJob and required query access](https://learn.microsoft.com/en-us/windows/win32/api/jobapi/nf-jobapi-isprocessinjob)
- [OpenProcess and handle ownership](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess)
- [Wait states and SYNCHRONIZE](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject)
- [ActiveProcesses accounting definition](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information)
- [Termination, signaling and object lifetime](https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process)
- [Job inheritance/nesting/no-breakaway](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
