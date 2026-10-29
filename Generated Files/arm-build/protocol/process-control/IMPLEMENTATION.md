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
