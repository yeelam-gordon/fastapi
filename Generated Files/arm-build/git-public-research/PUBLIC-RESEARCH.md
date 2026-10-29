# Windows ARM64: the `git submodule foreach` startup boundary

As of **2026-10-29**. Public-source research only; no internal search results,
private work items, credentials, local traces or unpublished timing measurements
are incorporated. This is a source/packaging explanation, not a measured
performance diagnosis. See [PROVENANCE.md](PROVENANCE.md) for immutable source
references, exact line ranges and release identity.

## Architecture answer

**An ARM64 Git installation is not an all-ARM64 POSIX toolchain.** Git for Windows
publishes `Git-2.56.0.3-arm64.exe`; its native Git environment is `clangarm64`.
MSYS2 explicitly distinguishes `/clangarm64` (aarch64, UCRT, LLVM) from `/usr`
(x86_64, Cygwin-based MSYS). All environments inherit the latter. Native Git and
x64 shell utilities in one installation are therefore consistent with the
documented design, not evidence that the whole Git package accidentally runs
as x64. [S1, S2, S3]

**Small ARM64 `bin` executables do not establish the shell's architecture.**
The installer copies `cmd\git.exe` into `bin\git.exe` and copies the *same*
`compat-bash.exe` into `bin\bash.exe` and `bin\sh.exe`. The compatibility
wrapper's resource explicitly targets `..\usr\bin\bash.exe`; resource dispatch
precedes filename-based fallback, and the launcher uses `CreateProcess`.
The Git wrapper selects the environment's actual `bin\git.exe`.
This explains why examining only the front-door PE is insufficient. Do not
mistake the source's separate BusyBox fallback for the full installer's
resource-configured shell path. [S3, S4]

These are source/package design facts. This research did not download or inspect
the release binaries and does not independently certify individual installed-file
sizes, hashes or machine fields. Packaging-source snapshots selected immediately
before publication are not a signed build manifest or reproducible-build proof.

## Why this command family has a different startup path

For the pinned **2.56.0.windows.3** Git source:

1. `submodule` is an external dashed command, whereas `submodule--helper` is
   registered as a Git builtin. The dispatcher launches `git-submodule`.
   Windows spawning code reads a script's shebang and looks up its interpreter.
   The exact selected interpreter image remains dependent on the installed
   package and effective search path. [S5]
2. `git-submodule.sh` starts with `#!/bin/sh`. Before `cmd_foreach` it uses
   `basename`/`sed`, sources `git-sh-setup`, verifies a work tree, computes a
   prefix and changes to the top level. Setup sources `git-sh-i18n` and invokes
   additional Git queries. This is not equivalent to a single native
   `git config` builtin invocation. [S6, S7]
3. `cmd_foreach` dispatches `git ... submodule--helper foreach`. The native
   implementation computes the module list and calls a callback for each listed
   submodule. The callback requests shell execution of the supplied command.
   **An empty traversal does not run that per-submodule command**, but the
   outer script and setup have already been entered. Nested `sh -c` text is not
   evidence that a corresponding nested process actually ran. [S6, S8]

Consequently, repeated empty `foreach` cleanup calls can repeatedly cross a
shell/setup boundary even without fetching or updating submodules. An x64 MSYS
shell boundary on an ARM64 host is a credible investigation target. The sources
do **not** allocate elapsed time between interpreter startup, utility children,
native Git children, scheduling, filesystem work, action orchestration or
instrumentation. Nor do they prove that emulation dominates the cost.

## Why checkout invokes this with submodules disabled

At `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`:

- `configureAuth()` first calls `removeAuth()` to clear previous values.
- `removeAuth()` calls `removeSsh()` and `removeToken()`. SSH cleanup recursively
  calls `removeSubmoduleGitConfig(core.sshCommand)`.
- Token cleanup recursively removes the HTTP extra-header key, then calls
  `getSubmoduleConfigPaths(true)` to discover submodule config files through
  `foreach` querying `remote.origin.url`, for credential-include cleanup.
- `removeSubmoduleGitConfig` supplies a quoted `sh -c` config query/unset
  command; `submoduleForeach` constructs `git submodule foreach`.

These three traversal entry points in each `removeAuth` invocation are not
guarded by the user's requested submodule-checkout setting. They serve cleanup
of possible existing state, rather than proving that this checkout requested
submodules or that its workspace contains any. They also explain why changing
`persist-credentials` is not a demonstrated way to eliminate startup cleanup.
[S9, S10]

## Existing upstream work and limitations

MSYS2's open **#3834**, “Port bash recipe to Windows Arm64,” explicitly describes
its proposed compiler/recipe work as a PoC pending upstream code-generation
changes. Discussion identifies a working MSYS2/Cygwin runtime as a prerequisite.
Git for Windows' maintainer stated in **#5292**, most recently in a 2026 closure
comment, that a fully native ARM64 MSYS2 runtime is still in the future.
The current environment matrix continues to list MSYS as x86_64. This supports
“not a fully supported native ARM64 MSYS stack,” not “ARM64 Git is unsupported,”
and provides **no delivery date**. [S2, S11, S12]

Existing fixes must not be relabelled as a new solution here:
MSYS2 **#4583/#4916** address `pacman`/GPGME double-fork hangs;
**#5000** backports an ARM64-canary crash fix. Their stated symptoms and paths
are not evidence of a fix for short successful `foreach` cleanup invocations.
Bounded public searches for Git-for-Windows `submodule startup`, ARM64
performance, and checkout `submodule foreach slow` did not identify a verified
matching performance fix. This is not an exhaustive “no fix exists” claim.
The exact release still has the shell script. [S6, S13]

## Facts, hypotheses and maintainer-friendly actions

| Kind | Statement / next action | Confidence |
|---|---|---|
| Fact | Native ARM64 Git and x64 MSYS tools are distinct environments; `bin` shell wrappers delegate rather than implement Bash. | **High**, documented/source design; installed bytes need separate receipts. |
| Fact | This pinned checkout cleanup enters `foreach` regardless of requested submodule checkout; an empty traversal still enters Git's outer script. | **High**, pinned source. |
| Hypothesis | Repeated shell/setup launches explain a material share of the command-family delay. | **Medium** as a mechanism worth testing; **low** as an unmeasured causal allocation. |
| Action, first | Checkout maintainers could consider a shared, native/public-interface discovery step to avoid redundant traversal entry when absence of relevant existing state is reliably established. | Candidate only; **medium** feasibility, no implemented or measured gain. |
| Action, second | Git/Git-for-Windows maintainers could reduce shell setup through a supported native public `git submodule` implementation; MSYS2/Cygwin maintainers own a full native runtime port. | Architecturally relevant; gain **unproven** and review cost higher. |

The first option belongs in common checkout/toolchain code, not an ARM-only
workflow fork. Review cost is **medium to high**: maintainers must preserve
reused/self-hosted workspaces, initialized and nested submodules, worktrees,
credential includes, SSH settings, failure handling and post-job cleanup.
`submodules: false`, a missing `.gitmodules` alone, or “new credentials were not
persisted” is not a sufficient proof that stale authentication state can be
ignored. A discovery query also has its own cost. Tests must include existing
submodules and stale credentials, not just a fresh empty repository.

A supported native Git implementation has **high** semantic/review cost:
quoting, recursive traversal, environment variables, error behavior, path
handling and existing callers must remain compatible. A complete ARM64 MSYS
runtime port is a broader upstream project, **very high** cost, not a local
checkout patch. Do not call Git's internal `submodule--helper` API directly
from an action as a shortcut.

### One discriminating experiment, not performed here

If existing process evidence cannot already settle the boundary, use one
credential-free, empty repository and the **exact CI Git build**. In a bounded
paired sequence compare public `git config --local --list` with
`git submodule foreach --recursive ':'`, recording process image paths,
parent/child start and exit events and per-process CPU. Keep host, working
directory, environment and cache order matched; do not dump auth config.
This tests whether empty-traversal shell/setup descendants account for the
incremental elapsed cost. It does not by itself isolate emulation from the
other costs of those descendants. No new probe or CI execution is authorized
or performed by this report.

## Architecture API caution

Microsoft documents `IsWow64Process2`'s `pProcessMachine` as
`IMAGE_FILE_MACHINE_UNKNOWN` when the target is **not a WOW64 process**;
`pNativeMachine` describes the **host**. Check API success before interpreting
either output. A zero process-machine value alone is not an affirmative
ARM64-image classification and must not overwrite independently recorded PE
headers or process image paths. Apparent disagreement requires reconciliation;
this research does not resolve it or establish a hybrid/emulation mode. [S14]

## Not justified

No claim that all Git is slow on Windows ARM64; no diagnosis of Actions Node
architecture from Git paths; no exact subprocess duration inferred from log
emission intervals; no attribution to antivirus/MDE, filesystem or networking;
no claim that an x64 PE alone proves the runtime mode or its performance cost.
No proposed internal-helper bypass, antivirus exclusion, shallow-history change,
or ad hoc foreign patch is an established fix. Local build evidence cannot
establish that the same descendants executed in CI.
