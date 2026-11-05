# Prospective process association; original CI remains failed/closed

Run 41947559106 at 664d5b29 is not rewritten or qualified by this correction.
Windows A1/B1 timings 38.715797/35.693773 seconds are unqualified, one-order
observations; BA did not run. No retrospective parent/creation identity exists
for Popen PID 2468 versus native CLI PID 1968. No gain or parity claim follows.
The parent's separate Mac hidden-attribute fix is retained unchanged.

The retained exact public CPython v3.13.15 source is
`cpython-3.13.15/venvlauncher.c`, from local tag revision
4061bc4c35f7c26f25264666d4ba083b93d2f6f9, SHA256
3e534d781343250e507656f7606256d0b8bc89c11f4c780fc482d94e7e00363a.
Its header describes launching the original executable using nearby pyvenv.cfg.
`CreateProcessW(executable, cmdline, ...)` creates another process;
`WaitForSingleObjectEx(pi.hProcess, INFINITE, FALSE)` keeps the redirector alive
until that child exits, then `GetExitCodeProcess` relays its status.
This proves the mechanism, not the missing original run's actual relationship.
The previous same-PID mock could never expose a separate redirector/native PID.

`cli_identity` now records the stable actual Popen handle's PID, real creation
FILETIME and image. A public coverage configurer records the actual native
Python process's corresponding identity and its currently live parent's PID,
FILETIME and image while the redirector waits. All APIs use explicit ctypes
signatures and documented FILETIME; no guessed structs, global scan, UUID birth,
canonical CLI argument change or application preload is introduced.
The actual Popen object is returned unchanged and rechecked at its original
wait. Association accepts direct identity or a live matching Windows venv
parent identity/image. Unavailable metadata, wrong birth/PID, duplicated or
unbound native CLI identity fails. Mac retains direct PID association without
inventing a creation clock. Every raw native shard is retained and inspected;
the complete non-pytest native CLI PID set must match the mapped Popen set.

`CLI-ASSOCIATION-PENDING.json` explicitly blocks CI admission. Original
SOURCEPINS and approval files are not regenerated. A new review/freeze/budget
is required; pending source hashes are not CI approval.

## Separate one-case local protocol (not executed during source correction)

From `Q:\fastapi`, after parent source review:

```powershell
& '.\Generated Files\arm-build\hobl-python-provision-screen\local-private\work\.venv\Scripts\python.exe' -B '.\Generated Files\worktrees\pipe-matched-ci\Generated Files\arm-build\pipe-matched-ci-readiness\cli_readiness.py' --source-repo 'Q:\fastapi' --output '.\Generated Files\arm-build\pipe-matched-ci-readiness\cli-readiness-02'
```

Requires the existing exact qualified local83 Windows ARM64 Python 3.13.15,
normal-GIL/non-JIT runtime, no global pycache prefix, and the existing local
864b569cf8453654fc3bc2c64108c0f644e2918c object. Output must be new.
The existing source helper makes a fresh complete tracked source with exactly
the qualified fixture changes. There is no network, wheel/bootstrap/download,
installation, build, ASGI or full HOBL.

Exactly `tests/test_fastapi_cli.py::test_fastapi_cli`, one worker, one stock
canonical coverage CLI child, no retries. Overall guardian allocation 120s;
native case allocation 60s, each includes 15s guardian cleanup reserve.
The protocol requires the actual Popen/native mapping, natural owned drainage,
native CTracer/source metadata, stock native CLI flush, resource closure,
source hashes and exact before/after local runtime/cache preservation.
Outputs are retained under the new directory, including result.json, identity
records, events, raw coverage and immutable copies, JUnit and guardian receipts.
It qualifies neither full-context equivalence nor Mac/service/physical timing.

## V2 postwait key correction

The original readiness-01 remains failed: its observer queried an exited
process's image after the canonical test waited, producing WinError 31.
Both guardian families drained naturally without timeout; that does not
qualify CLI association or imply a canonical CLI functionality failure.
V2 captures image provenance once before wait while the process is live.
After wait, only PID and real creation FILETIME are read through the retained
actual Popen handle. Image and numeric-PID reopening are forbidden on that path;
missing/changed keys fail without fallback. Native current/live-parent image
requirements are unchanged. Only output 02 may be used after new source
review and freeze. The original pending plan is retained separately.

Separately, canonical SOURCE_DATE_EPOCH=1700000000 and complete reference
archive-header validation remain a required new-route-only correction.
They were not changed during this narrow process-lifetime fix.
