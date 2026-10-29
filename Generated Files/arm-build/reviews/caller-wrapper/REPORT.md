# Independent caller semantics and maintenance review

Reviewed `7df0adb88f67e59e73abbac698fa6c5f426e163f`, including the attributed
POSIX-group correction and SDK source/hook correction already in its base.
Owned changes are confined to this review directory.

**Disposition: bounded caller-contract PASS, with one low-severity policy/
performance opportunity (CW001). No new blocking caller defect demonstrated.**
This is not integrated experiment readiness, process-family certification,
artifact revalidation, parity evidence, or release approval.

## CW001 — SDK ignores the intended environment-only bytecode suppression

- **Location:** `protocol/isolated_build.py:129,225–240`;
  `candidate/build.py:3–13,95–96`.
- **Severity:** low, nonblocking optimization/policy clarification.
- **Confidence:** high in flag semantics and the reproduced write; unknown
  savings and actual backend write count.
- **Expected:** if `PYTHONDONTWRITEBYTECODE=1` is intended to suppress import
  cache writes in the fresh caller, the SDK interpreter should honor that
  effective policy.
- **Observed:** SDK argv contains `-E -s`, not `-B`. CPython `-E` ignores
  `PYTHON*` environment settings, including that variable. The tiny-module
  child reports `sys.dont_write_bytecode=false` and creates one real `.pyc`.
  The environment-only control and explicit `-B -E -s` control create none.
  `bytecode.json` retains flags, actual runtime and observed files.
- **Reproduce:** run the owned `probe_bytecode.py` with the master interpreter,
  as in the commands below. It creates only a public, trivial module beneath
  an exclusively owned Q: child, then deletes that child in `finally`.
  No candidate import, backend installation, packaging build, protection
  change, or timing benchmark is performed.

The candidate imports local `selector`, then `ops` and PDM backend modules;
there is no explicit bytecode suppression in its CLI. Therefore bytecode writes
are enabled for those imports when caches are absent and locations writable.
The tiny-module experiment demonstrates the enabling condition and a real
write, **not a measured inventory of PDM writes in an actual SDK build**.
The identity child also uses `-I`, which implies ignoring Python environment
variables; it is not evidence that the variable works there.

The published wrapper contract does not promise zero `.pyc` files, and recording
that an environment variable was set is truthful. This is not an artifact
correctness failure. Backend caches in the deleted fresh environment cannot
benefit a subsequent invocation; within-process repeated imports normally use
`sys.modules`. Conversely, helper-module caches can live in the persistent
candidate directory, and base-stdlib caches are not necessarily ephemeral.
Do not describe every potential write as disposable backend work.

**Minimal recommendation:** if suppressing unused fresh-backend cache writes
is desired, explicitly add `-B` to the SDK interpreter argv; do not remove `-E`
or invent a wrapper framework. This ordinary CPython flag should not alter
canonical package payloads: backend/helper caches are outside that source.
Artifact equivalence after any producer change still requires its focused
verification; it was not rerun here. Do not promise speedup or make the change
on this review's authority. Mac has the same CPython flag semantics, but no Mac
probe or benefit is measured. This is standard interpreter behavior, not a new
bytecode technique or the prior frontend/bytecode patch. No MDE/scanner,
ISA, or causal performance claim follows.

## Caller contract checks

- **Freshness and placement:** `execute` exclusively creates a UUID environment
  next to the new report; scratch and venv are underneath it. `TEMP`, `TMP` and
  `TMPDIR` target scratch; uv uses the explicitly supplied warm cache.
  Creation, installation, identity, SDK and owned-directory deletion all occur
  inside the invocation. Q: fixtures are not a C: performance result. Actual
  C:/NTFS enforcement belongs to the outer harness, not this general wrapper.
- **Installer:** explicit uv executable, `--no-config --offline --cache-dir`,
  explicit Python, no downloads; installation uses `--require-hashes`,
  `--no-index`, binary-only wheels and the exact PDM 2.5.0 lock. Lock hash
  matches the already preserved official wheel receipt. No new offline
  installation was run.
- **Identity is executed, not merely declared:** the `-I -c` child checks
  actual `sys.prefix` against the fresh venv, a distinct base prefix, exact
  3.13.15, native ARM machine/platform, disabled user site and installed
  `pdm-backend` 2.5.0. Outer `-O` does not propagate an optimization flag to that
  child. Its assertions are therefore not disabled by our optimized wrapper
  fixture run. The gate cannot be replaced with a report label.
- **Independent historical identity linkage:** read the three preserved raw
  `identity.log` outputs, not just the producer summary, and checked equality
  with each receipt plus its owned-root prefix. All three are distinct native
  win-arm64 CPython 3.13.15/PDM 2.5.0 caller prefixes. Raw/report SHA256 and
  actual identities are in `historical-identity.json`. This replays earlier
  process output; it neither runs a new caller nor proves the group correction
  was exercised by those older builds. `inputs.json` separately records the
  actual master validation runtime and raw current-worktree input hashes.
- **Failures:** original subprocess exit/raw log survive; cleanup failure
  appends a second error and forces failure. Existing success/failure fixtures
  pass normally and optimized. Only the exclusively created environment is
  deleted; the supplied source, output, wheelhouse and warm cache are retained.
- **Collisions:** report creation is exclusive; source/output report placement,
  preexisting output, and cache/dependency paths inside source/output are
  rejected before launching tools. New independent collision subcases cover
  these boundaries. This does not claim arbitrary hostile filesystem-race or
  symlink protection.
- **Environment/credentials:** Python path/home and inherited venv overrides
  are removed; user-site imports are disabled. The recorded environment is a
  whitelist of changes, not a dump; a sentinel environment key is absent from
  the report. The execution environment is still `os.environ.copy()` minus
  four keys: credentials and unrelated settings can remain inherited. This
  meets the stated record-minimization contract, **not** an execution-env
  allowlist or a guarantee that arbitrary raw child logs never expose secrets.
  No credential values were inspected or security changes proposed.
- **PP001:** read both the original contract and committed correction
  verification. Its closed receipt-validation result is not reopened here;
  directory cleanup/identity receipts do not certify process containment.

## Process ownership scope

Current POSIX `Popen` sets no new session/group and has zero Windows creation
flags there; it therefore remains compatible with an outer owned POSIX group.
It never calls inner `killpg`. On interruption it kills and reaps only its
direct child, preserving the original interruption in the tested ordinary
cleanup path. That is explicitly **not standalone whole-family cleanup**.
Windows retains its existing process-group flag without breakaway.

The existing mocked POSIX tests pass normally and optimized. No native POSIX
process ran, and this worktree does not independently execute the separately
reviewed outer helper (`935` context). Outer group/job setup, descendant drain,
hard-kill report loss and integration remain that lane's responsibility.
Its already known pending cleanup issue is not duplicated as a caller finding.

## Commands and durable receipts

From this worktree, master Python:
`Q:\fastapi\Generated Files\arm-build\.venv\Scripts\python.exe`.
Review scripts/logs are under `Generated Files\arm-build\reviews\caller-wrapper`.

| Validation | Result |
|---|---|
| Python `-B probe_bytecode.py` | exit 0; `bytecode.json`, three controls |
| Python `-B test_review_guards.py -v` | 8 tests PASS; `tests-normal.log` |
| Python `-B -O test_review_guards.py -v` | 8 tests PASS; `tests-optimized.log` |
| Existing master Ruff `check --no-cache` on wrapper, wrapper tests and both review scripts | PASS; `ruff.log` |
| `git diff --check` | PASS |

The eight tests comprise all six inherited producer methods plus two independent
methods (including five collision subcases). Tests use mock children except the
public tiny-module probe. Existing master tools were read-only; no dependency
install, subagent, CI, push, producer edit, real C: build or timing matrix.
Scratch children were removed. All validation here is review cost, not baseline
build time or an addition/subtraction to any retained sample wall.
