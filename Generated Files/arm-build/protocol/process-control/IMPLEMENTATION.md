# Approved bounded ownership helper

The original `REPORT.md` is preserved unchanged. This implements the root's
subsequent approval, not authorization for CI, benchmarks, or integration.

## Producer API

```python
from dataclasses import asdict
from owned_process import run_owned

receipt = run_owned(
    argv, cwd=sample_directory, env=child_environment,
    stdout_path=stdout_log, stderr_path=stderr_log, timeout=120,
)
sample["process"] = asdict(receipt)
if not receipt.succeeded:
    raise RuntimeError("Invocation failed or family ownership/cleanup incomplete")
```

`Receipt` is a frozen dataclass: `returncode`, `timed_out`, `command_wall`,
`infrastructure_wall`, `ownership_established`, `survivors`, `cleanup_complete`,
and `errors`. `None` means unavailable, not zero. Timeout can leave returncode
unknown because the family is then terminated externally. A successful root
exit with a surviving family is rejected even when cleanup subsequently works.
Original nonzero status is preserved independently of cleanup errors.

**The harness producer must stop its entire sample loop unless `succeeded`.**
This standalone helper does not schedule samples. Persist the receipt and
unfiltered logs, not `env`; do not infer success from returncode alone. Add the
helper's exact bytes/hash to the required frozen input inventory. No harness,
wrapper, SDK, comparator, or shared root inputs were edited in this lane.

The child command runs in the supplied cwd/environment. The control spec exists
only in an anonymous stdin pipe and contains argv/log paths/timeout/job name,
not the environment. Logs are written as raw bytes; identical stdout/stderr
paths deliberately merge the streams. Receipt contains no full argv/env.

## Ownership and measurement

Both platforms use the same small trusted Python supervisor. Its startup and
containment setup precede the target timer. `command_wall` starts immediately
before the actual target spawn and ends after root wait, supervisor exit,
family checks/termination/drain and handle cleanup. These post-command costs
are charged, not subtracted. `infrastructure_wall` is the preceding setup
duration. Both clocks use CPython's system-wide `perf_counter`. A broken
supervisor may make both clocks unavailable; that result cannot succeed.
Disclose and include infrastructure separately in experiment cost totals.

Windows uses a random named job with KILL_ON_JOB_CLOSE and no breakaway flags.
The supervisor opens it, assigns **itself before spawning the target**, and
closes its own handle. The controlling parent retains the sole job handle.
Thus no suspended-thread or private Popen handle operation is needed. The
supervisor uses the standard CPython base-prefix `python.exe` on Windows:
observed venv-redirector lifecycle cleanup otherwise masks survivor detection.
Its setup still remains separately itemized on both platforms.

The parent checks job accounting after supervisor exit. Surviving processes
reject success. For termination, documented job-only PID enumeration obtains
synchronization handles before TerminateJobObject, waits on those known
processes, and verifies zero active processes with a bounded drain. This
enumerates only the owned job, never system processes or private environment
details. The extra handle wait matters: initial proof observed zero active
accounting before a known process's termination handle became signaled.
Kill-on-close remains the fallback on a query/drain error, with
`cleanup_complete=False`, not a claim that fallback termination was verified.
Limits bound waits, not arbitrary stalled OS calls.

At approximately 300 lines including dataclass, typed SDK structures, checked
ctypes declarations, supervisor and both OS branches, this exceeds the
aspirational 180 lines. It introduces no new architecture/dependency, watcher
thread, private API, supervisor framework, or machine setting. The documented
SDK layouts and asynchronous-termination checks account for the difference.

**POSIX integration prerequisite:** the target family must stay in the
supervisor's new session/group. The producer must remove the wrapper's current
per-phase `start_new_session=True` for contained invocations; otherwise SDK
phases can escape and this helper must not be used to claim SDK containment.
The helper does not support deliberately detaching commands. Group existence
and SIGKILL are bounded/owned-only; lingering zombies or permission errors fail
closed rather than claiming success. POSIX parent-crash cleanup is not promised.
Windows nested-job assignment can fail under incompatible inherited job
restrictions: fail before target spawn, with no silent fallback. Hosted runner
compatibility remains an integration gate, not established by local success.

## Executed proof

Native Windows ARM64 CPython 3.13.15. Interpreter:
`Q:\fastapi\Generated Files\arm-build\.venv\Scripts\python.exe`.
Ran `protocol\test_owned_process.py` normally and with `-O`:
**9 tests, exit 0 each**, approximately 4.5 seconds per invocation.
`git diff --check`: exit 0. No dependency installs.

Real helpers are exclusively the test file's explicit `--helper` roles:
normal, failure, timeout, intermediate and sleep. They write their own PIDs
under a unique project-local proof directory. Proof covers byte-exact logs,
nonzero status, timeout with a live family, fast parent plus exited
intermediate and live grandchild, and checks/cleans only these known PIDs.
Final proof directories were removed. Setup/query/drain failures and POSIX
group signaling use mocks; no Mac execution is claimed.

Initial attempts failed: isolated helpers needed an explicit local module
path, psutil was absent (replaced with standard-library known-PID handles),
venv launchers masked survivors, and accounting-only cleanup was too early
for process-handle signaling. These were corrected before the final two
passing runs. Ruff was unavailable at the attempted executable/module paths;
no lint success is claimed. No benchmark, CI, push, security change, source
build, or unrelated process enumeration was performed.

Confidence: **high** for demonstrated local Windows paths and fail-closed
receipt semantics; **medium** for hosted nested-job compatibility; **low**
for unexecuted macOS runtime behavior. Integrated PP003 closure remains
conditional on POSIX wrapper inheritance, frozen input hashing, and harness
abort/report integration.

## Public API basis

- [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects):
  inheritance, nesting, accounting and kill-on-close.
- [AssignProcessToJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject):
  assignment before target creation and inherited-job constraints.
- [Extended limits structure](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information),
  [accounting structure](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information),
  [job-only PID list](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list),
  and [TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject).
- [Python 3.13 subprocess](https://docs.python.org/3.13/library/subprocess.html):
  public Popen, communicate/wait timeouts and start_new_session.
- [Python perf_counter](https://docs.python.org/3.13/library/time.html#time.perf_counter)
  and [owned POSIX group signaling](https://docs.python.org/3.13/library/os.html#os.killpg).

## PC001 follow-up: preserve cleanup failure evidence

Independently reproduced the review's two injected failures before editing:
the new setup/close regression lost the original diagnostic, and a stdin
close exception escaped instead of returning the command's status 7.
Both reproductions used mocks only.

The bounded correction retains the original setup exception, attaches any
secondary job-close failure as a Python exception note, and includes those
notes in receipt errors. Each supervisor pipe close is now attempted
independently; a failure appends a diagnostic and marks cleanup incomplete
without discarding the original invocation error or returncode. API, timer
boundaries, Windows job ownership and POSIX group scope are unchanged.

Final validation: **11 tests passed normally and with `-O`, exit 0 each**;
`git diff --check` passed. The two added regressions require original and
secondary diagnostics, preserved status 7, all three close attempts and
fail-closed cleanup. Existing tiny Windows lifecycle proofs still pass;
POSIX remains mocked/unexecuted on macOS. No leftover proof directories.
No CI, build, push, dependency install or producer integration.

## Approved LOCAL-OWNERSHIP-004 liveness correction

Positive Windows accounting now triggers a complete documented owned-job
membership query and public process-handle wait-state checks, not an immediate
live-survivor classification. Only the known, already-waited supervisor launch
PID is excluded; its Windows Popen process object/handle remains held during
observation. No guessed launcher, process name, or arbitrary grace interval
is used.

Every other member is opened with SYNCHRONIZE plus QUERY_LIMITED_INFORMATION
and validated with IsProcessInJob on that exact handle. WAIT_OBJECT_0 means
terminated; WAIT_TIMEOUT means live and still rejects success. Failed access,
membership identity mismatch, failed wait, incomplete enumeration and newly
appearing members all fail closed. ERROR_INVALID_PARAMETER on OpenProcess is
recorded as departed, but acceptance additionally requires absence from the
complete second snapshot; reappearance is unknown, not assumed PID identity.

All opened member handles remain held across the second snapshot, preventing
their process identities from being recycled during validation. No new PID
may appear in that snapshot. If every observed non-supervisor member is
terminated/departed and membership has no unexplained additions, there is no
observed executing member left to create another child. This is a bounded
two-snapshot validation, not a repetition-until-success loop.

Receipt adds a defaulted `liveness` tuple containing diagnostic dictionaries
when accounting is positive: member IDs/states, newly seen IDs, and any
query/wait/close error. It contains no environment or private process details.
Existing receipt fields and succeeded predicate remain unchanged. Producer
serialization should retain this additive evidence field. Job ownership,
KILL_ON_JOB_CLOSE, POSIX scope, and whole-command clock are unchanged.

The original frozen failure remains an unclassified observation. This
corrects a source/API inference; it does **not** prove that accounting
reference lifetime caused LOCAL-OWNERSHIP-004. The old frozen receipt is not
reclassified or replaced, and this commit authorizes no preflight/campaign.

Validation uses the supplied read-only managed native ARM64 interpreter.
Focused mocked regressions cover positive accounting with terminated/live
members, unknown access/identity/wait/enumeration, concurrent new membership,
departed-PID reappearance, and keeping identity handles until validation.
Existing real normal, genuine fast-root/grandchild leak and timeout gates,
plus the project-local `process-control\test_parent_death.py` known-PID gate,
are run before commit. No new benchmark, CI, C: write or system process scan.

Final results: **14 ownership tests passed normally and with `-O`**, exit 0
each; **one real parent-death gate passed normally and with `-O`**, exit 0
each. All used the supplied managed interpreter and Q: scratch, with only
explicit owned PIDs touched. `git diff --check` passed. Confidence is high
for these demonstrated Windows paths, medium for the bounded membership
argument pending independent review, low for unexecuted macOS runtime.
Original LOCAL-OWNERSHIP-004 causality remains unestablished.

## PC002: final bounded termination-cleanup repair

Independently reproduced the injected failure before editing: a failed first
CloseHandle skipped subsequent pinned handles, and replaced a primary
TerminateJobObject failure in receipt diagnostics. No native failure is claimed.

`_Job.kill` now attempts every pinned-handle close independently. Secondary
close errors are attached as notes to the original termination/wait exception,
or raised together when termination itself succeeded. The existing receipt
cleanup handler retains those notes, the original command status and all
cleanup failures. Cleanup stays incomplete; job-close fallback is not silently
represented as verified cleanup. Membership, ownership, receipt API and timer
behavior are unchanged.

Focused injected regression covers both successful and failing termination,
two failed closes plus a third successful close, preservation of status 7,
original termination error, every secondary diagnostic and final job close.
With the supplied managed interpreter, **four mock-only focused tests passed
normally and with `-O`, exit 0 each**, including PC001 and member-state guards.
`git diff --check` passed. No additional native loop, diagnostic campaign,
build, benchmark, CI, push, dependency or infrastructure was introduced.

This helper is measurement hygiene only, not a performance improvement or
adoption proposal. The private-PDM SDK remains diagnostic-only, and the
campaign remains paused for the root's generalizability/ecosystem review.
Work stops after this repair. Confidence in this narrow injected-error fix:
high; original LOCAL-OWNERSHIP-004 causality remains unknown.
