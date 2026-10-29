# PP003: bounded lifecycle adjudication

Reviewed research HEAD `7b85725ef52225f6d8159784dc01c1264170824e`.
Owned scope: this report only. No producer edits, benchmark, CI, push, real
child-process reproduction, process enumeration, or protection changes.

## Disposition

**Retain medium severity. High confidence in incomplete ownership and the
timeout race; medium confidence in practical incidence; low confidence that
the successful-fast-parent fixture represents a supported successful build.**

Do not implement a general Win32 supervisor to satisfy that mock. Equally,
do not close PP003 with “our tools wait” if claiming guaranteed timeout cleanup.
The minimal next step is a root decision on the scope of the guarantee:

1. **Recommended for the existing declared cleanup contract:** approve a small,
   documented OS containment change in the harness/wrapper lanes, with the
   focused acceptance tests below. No production API is supplied here.
2. **Smaller explicit scope, if the root chooses it:** retain known synchronous
   success-path evidence, label failure cleanup best-effort/ownership unknown,
   abort the entire allocation on any failure, and prohibit subsequent valid
   samples or local reuse until ownership is independently resolved. This can
   protect interpretation of later samples by not taking them; it does **not**
   establish local leak-free cleanup. Do not silently present it as option 1,
   or authorize unattended local failure tests on this shared machine.

If reliable containment is disproportionate to this one experiment, option 2
or deferring the experiment is preferable to a bespoke supervision framework.
Neither current local timing gains nor this report authorize either change.

## Challenge the counterexample against the actual call chain

- `measure_pairs.py:154–211` polls ancestry only while the launcher is alive.
  The existing PP003 fixture supplies a successful launcher already exited,
  plus an independently live child. It proves an acceptance hole **conditional
  on that state**, not that pinned uv/PDM produces that state.
- `isolated_build.py:23–54,151–241`: create/install/identity/SDK phases wait
  synchronously for their direct child. The wrapper does not deliberately
  daemonize. It marks success only after SDK exit and artifact checks, then
  performs environment cleanup. A cleanup receipt proves directory cleanup,
  not process-family emptiness.
- `candidate/build.py:65–119` calls PDM sdist and wheel builders in-process.
  `candidate/ops.py:14–44,55–77` uses a context-managed ThreadPoolExecutor;
  reader close unwinds the context and waits for running readers. Those
  workers are threads, not detached OS children. Cancellation alone is not
  the join guarantee; context exit is.
- `candidate/selector.py:19–53` rejects custom backend paths, build settings,
  project hooks/entry points, and non-file dynamic version sources. Arbitrary
  hostile backend commands are not an appropriate success-path model for
  this SDK. Baseline B separately depends on the frozen source/backend;
  the SDK guard is not a guard executed by B.
- PDM 2.5.0 `Builder.build` calls clean/initialize/collect/build/finalize and
  returns synchronously [P1]. uv 0.13.6 `PythonRunner.run_script` reads backend
  output and explicitly awaits child exit [U1]. These are affirmative
  lifecycle evidence, not a proof about every uv error branch or every
  environment. No ordinary supported successful orphan path was demonstrated.

Consequently, a normal fast successful process need not be rejected merely
because it ran between polling ticks. Counting “was ever observed” is not a
valid mandatory success condition for these synchronous command families.
An extra ancestry census after parent exit, shorter polls, or `taskkill /T`
after the root has disappeared does not recover lost ancestry.

## Reachable supported failure, without hostile hooks

The timeout is external to synchronous waiting:

1. The harness sees an alive wrapper and takes its ancestry census.
2. Before the next instruction/check/kill, the wrapper starts its next
   legitimate phase, or uv starts a legitimate PEP 517 Python backend.
3. The 120-second deadline is reached. The harness terminates only remembered
   descendants, then kills the launcher. The newly started child was never
   remembered and can continue.

No undocumented behavior or malicious command is required. OS scheduling or
stalled I/O can place a normal phase boundary at the deadline. The actual
probability is unmeasured; normal multi-second builds need not resemble the
fixture's immediate successful exit. There is also no freeze on child creation
during the current child-first cleanup loop.

Killing the wrapper externally does not execute its Python exception/finally
cleanup. On Windows its CREATE_NEW_PROCESS_GROUP is a console grouping flag,
not job ownership. On POSIX the wrapper explicitly starts each phase in a
**new session**; simply adding one outer process group would miss those phases.

The current measurement loop already raises immediately after a failed result
(`measure_pairs.py:738–750`), outside its remaining sample loop. Preserve that
behavior. It limits known failure contamination but does not detect an
unobserved surviving child after a nominal success, nor prove local cleanup.

## Smallest documented containment if the stronger contract is retained

Contain this fixed invocation family, not arbitrary services, WMI launches,
hostile breakaway, or unrelated processes. Do not change priority, affinity,
resource limits, machine policy, or protection.

- **Windows:** one unnamed noninherited job handle per invocation, with
  JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE and no breakaway flags. Put the root in
  that job **at creation**, using documented
  PROC_THREAD_ATTRIBUTE_JOB_LIST/STARTUPINFOEX [W2], or documented
  CREATE_SUSPENDED + AssignProcessToJobObject + ResumeThread when a supported
  binding owns the returned primary-thread handle. Assigning an already
  running `Popen` is racy. Use proper SDK structures and checked error returns;
  no NtResumeProcess, guessed layouts, private Popen handle tricks, or
  name-based kills. Prefer an existing maintained binding; dependency/launcher
  choice requires root approval rather than inventing a library here.
- Job membership normally propagates through CreateProcess independently of
  parent lifetime, and nested jobs are supported on current Windows [W1].
  Check real runner compatibility; assignment failure is fatal, not permission
  to fall back silently. Keep the controlling harness outside the child job.
- After root exit, use documented job accounting to require zero active
  processes before accepting success. Any survivor rejects that invocation;
  terminate the job, then bound and verify its drain. On timeout/failure,
  terminate the job and verify drain before returning cleanup-complete.
  Kill-on-close is a backstop, not evidence that termination already finished.
  Do not assume a job handle becomes signaled on every ordinary empty-job
  transition; the documentation gives a narrower signaling condition [W1].
- **macOS:** create one session/process group for the timed root before exec;
  keep this fixed family's descendants in it. The wrapper's current
  per-phase `start_new_session` must not escape that group. Use documented
  group signaling and bounded liveness checking, handling/reaping exited
  children rather than mistaking zombies for executing work. Scope explicitly
  excludes descendants that deliberately create a new session. Test the actual
  frozen command chain rather than claiming arbitrary process-tree containment.
- On spawn/setup/query/kill/drain failure or uncertain ownership: persist
  diagnostics, mark invocation failed and cleanup unknown/incomplete, abort
  the job. No replacement or subsequent valid sample. Preserve the original
  error alongside cleanup errors. A bounded cleanup deadline can prevent
  indefinite waiting; it cannot promise every OS operation completes.

This needs no per-process watcher threads, completion-port framework, system
process sweep, or new supervisor protocol. If the required supported binding
is unavailable, stop and adjudicate cost rather than expanding this lane.

## Measurement and acceptance

Apply the ownership boundary to B/S1/S3 on **both** OSes. Charge creation,
launch, liveness verification and cleanup inside the same outer wall boundary;
do not put a Python helper startup only in Windows' measured path and hide it
as infrastructure. Prefer in-process containment around the existing command.
Report unavoidable OS-specific orchestration, retain the pinned family scope,
and do not subtract a guessed overhead or interpret it as backend performance.
Existing SDK/wrapper correctness and freshness results are not contradicted
by PP003; no artifacts or performance samples were regenerated here.

Before calling a producer fix ready, test: normal synchronous child exit;
fast root with surviving owned child; intermediate parent exit; timeout during
legitimate child creation; failed containment setup; failed/late drain; and no
next sample after any failure/unknown ownership. Tiny helpers may be used only
with explicit source/PID receipts and immediate cleanup of their own PIDs.
Also test the POSIX nested-session issue and real Windows runner nested-job
compatibility. These are future gates, **not executed evidence** in this report.

## Executed evidence and primary references

Interpreter: `Q:\fastapi\Generated Files\arm-build\.venv\Scripts\python.exe`.
From this worktree, ran the existing review file with selector
`ReviewCounterexamples.test_successful_fast_parent_never_checks_or_kills_owned_child`
normally and with `-O`: **1 test passed in each invocation**. Both assert the
undesirable current acceptance; neither launches a real process or proves a
fix. An initial selector `ProtocolReview...` failed because that class does not
exist; the corrected invocations above passed. No dependencies installed.

Primary sources read on 2026-10-28 (public source only):

- [U1: uv 0.13.6 frontend](https://github.com/astral-sh/uv/blob/0.13.6/crates/uv-build-frontend/src/lib.rs#L1271-L1369):
  PythonRunner and awaited child exit at 1360–1364.
- [P1: PDM 2.5.0 base](https://github.com/pdm-project/pdm-backend/blob/2.5.0/src/pdm/backend/base.py#L203-L224):
  synchronous builder call chain.
- [W1: Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects):
  inheritance, nested jobs, termination, accounting, kill-on-close and signaling.
- [W2: UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute):
  documented job-list process-creation attribute (Windows 10+).
- [R1: GitHub runner JobExtension](https://github.com/actions/runner/blob/main/src/Runner.Worker/JobExtension.cs):
  initialization at 588–599 enables process cleanup by default and stamps a
  tracking environment value; **FinalizeJob** at 891–938 enumerates new
  processes, compares the tracking value and attempts termination. This is
  mutable upstream context, not a receipt for the eventual runner revision.
  It runs at job finalization, not between samples; exceptions are logged.
  It supplies neither local-machine ownership nor a between-sample barrier.

**Final recommendation:** approve only the bounded containment design if
guaranteed family cleanup remains required. Otherwise explicitly narrow the
contract and stop on unknown cleanup; do not claim PP003's ownership guarantee
was fixed merely because synchronous successful builds pass.
