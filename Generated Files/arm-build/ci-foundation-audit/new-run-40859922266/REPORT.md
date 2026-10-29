# Saved metadata audit — analysis run 40859922266

## Boundaries and matched scope

Run [40859922266](https://github.com/yeelam-gordon/fastapi/actions/runs/40859922266)
failed. Windows collected diagnostics; Mac failed collector preflight and
skipped both Git context and backend collection. **There are no paired normal
build/backend measurements. The unequal job walls are NOT a speed comparison.**
Failed preflight/collection steps are not ranked as comparable workloads.
No new CI, builds, profiling, network tests or source edits were performed.

The two successful checkouts on each host are paired separately:

* **Tools sparse:** `675fd789e686c2fbd068c2e921e8a7b76d4dfeda`;
  filtered fetch and sparse checkout, first checkout step (3).
* **Package full:** `79cab5bed28b24d92c185d236feb33f5783dfeb3`;
  unfiltered fetch and sparse-checkout disabled, second checkout step (4).

Do not compare old full checkout's 3,390-file work to this run's tools sparse
checkout. Source SHAs, scope and collector configuration changed. Old
`foreach` interval observations remain a qualitative lead, not a pooled
paired sample or a causal diagnosis.

## Existing paired wall intervals: prioritize absolute seconds

One observation per scope/phase/OS. Workflow API timestamps have one-second
resolution. Console group intervals are finer log timestamps, not CPU time.
Containers overlap: **do not sum steps, subgroups, command windows or medians.**

| Workflow step | Windows s | Mac s | Gap s |
|---|---:|---:|---:|
| Package full checkout | 17 | 3 | **14** |
| Tools sparse checkout | 14 | 3 | **11** |
| Native Python + locked tools | 11 | 7 | **4** |
| uv setup | 3 | 1 | **2** |

Within the checkouts, console-group absolute-gap ordering is:

| Scope / group | Windows s | Mac s | Gap s |
|---|---:|---:|---:|
| Package full: checkout ref | 5.936918 | 0.636730 | **5.300188** |
| Tools sparse: setup auth | 5.457849 | 0.386559 | **5.071290** |
| Tools sparse: remove auth | 4.222902 | 0.362429 | **3.860473** |
| Package full: setup auth | 3.984478 | 0.324309 | **3.660169** |
| Package full: remove auth | 4.186860 | 0.654124 | **3.532736** |
| Tools sparse: fetch | 1.224801 | 0.501291 | **0.723510** |
| Tools sparse: checkout ref | 1.383997 | 0.911769 | **0.472228** |
| Package full: fetch | 2.094640 | 1.715956 | **0.378684** |

Console pointers: Windows tools groups 132–217, package 260–415;
Mac tools 958–1021, package 1078–1138. Exact subgroup endpoints,
signed gaps, ratios and command emissions are in `paired-metadata.json`.
The action's `Run actions/checkout...` command-rendering group itself is
not treated as an execution timer.

### Auth command pattern, not process-duration attribution

Within setup/remove-auth, checkout-ref and fetch groups, each source scope
on each OS emits exactly **28 Git commands**: 19 config, 6 submodule foreach,
1 checkout, 1 fetch, 1 other. This intentionally excludes helper commands
outside those selected groups and the separate post-job cleanup. All 112
selected command emissions retain literal argv and original line numbers.
Nested Git/shell text in a `foreach` argument is not separately observed
process execution.

Windows tools-scope `foreach` emission windows are
**2.495408, 1.280613, 1.240927, 1.196049, 1.207422, 1.250174s**;
Mac counterparts range **0.079350–0.138993s**. Package-scope Windows
counterparts range **1.172981–1.234988s**, Mac **0.078781–0.186431s**.
The visible pattern is repeated same-class windows, not more emitted
commands on Windows. These are command-log-to-next-command/group-end
intervals; they include unallocated action/Node/launch/logging/filesystem
space and **are not exact process durations**. First intervening log events
may be action messages, not child stdout. Every `exact_process_seconds`
field is explicitly null.

### Bootstrap receipt substeps

Separately recorded native Python command walls, one sample each:

| Command | Windows s | Mac s | Gap s |
|---|---:|---:|---:|
| Install Python | 2.851294 | 2.446475 | **0.404819** |
| Find Python | 0.472184 | 0.119187 | **0.352997** |
| Probe Python | 0.257537 | 0.104673 | **0.152864** |
| Create environment | 0.043085 | 0.012857 | **0.030228** |

These are not the complete locked-tools provisioning step, nor a
decomposition of the difference between step-level medians.

## Runtime and hardware: new actual evidence, precisely scoped

Both uploaded **actual GitHub Action process** receipts identify
**Node v24.21.0, runtime arm64**, from the runner's
`externals\node24\bin\node.exe` / `externals/node24/bin/node`.
This is not a PATH Node inference. The recorded action process is native
ARM64 on both hosts; the receipt is not a process-architecture trace of
every checkout child. It supports **no Actions Node emulation claim**.
Windows inventory separately identifies PATH Node **v24.22.1**, at
`C:\Program Files\nodejs\node.exe`; do not conflate the two runtimes.

The new action receipts expose Windows **4 logical CPUs**, model string
**Cobalt 100**, and Mac **3 logical CPUs**, **Apple M1 (Virtual)**.
Windows memory reported is **17,169,387,520 bytes**, Mac
**7,516,192,768 bytes**. These are actual new-run OS/runtime-reported values,
not extrapolation from the old Model D49 identifier, and do not establish
equal physical-host resources or hardware causality.

## Windows Git candidates versus actual execution

Uploaded Windows inventory records:

* PATH Git `C:\Program Files\Git\bin\git.exe`, version
  **2.56.0.windows.3**, PE **arm64** header.
* `git --exec-path` reports `clangarm64\libexec\git-core`.
* Candidate `git-submodule` is a script with **`#!/bin/sh`**.
* Candidate `bin\sh.exe` and `bin\bash.exe` have **arm64** headers.
* Candidate `usr\bin\sh.exe` and `usr\bin\bash.exe` have **x86_64** headers.
* Candidate `git-submodule.exe` and `git-submodule--helper.exe` at the
  inspected exec-path locations are unavailable (`FileNotFoundError`).

Every helper is labelled **candidate/not-proven-executed**. File presence,
shebang and binary headers do not identify which helper/process actually
ran or whether an x86_64 candidate was executed. Missing candidate paths
do not prove helper functionality is absent elsewhere. **Mac helper
inventory/execution profiles were not collected.**

Windows standalone read-only Git context has three samples per command:

| Command | Windows median s | Range s | Mac |
|---|---:|---:|---|
| version | 0.0443632 | 0.0434434–0.0482953 | unavailable |
| local config read | 0.0457117 | 0.0456702–0.0489130 | unavailable |
| recursive submodule foreach no-op | 1.2049987 | 1.1998760–1.2224702 | unavailable |

The receipt says `.gitmodules` is absent in this package checkout. This
context is **not** the auth subprocess timer and supplies no Windows–Mac
delta. No delta is invented from the missing Mac collection.

## Provenance and remaining limits

New actual-action environment records Windows ImageVersion
**20261026.197.1**, Mac **20260907.0337.1**. The uploaded inventory explicitly
preserves the historical **20261025.196.1 console versus 20261026.197.1
bootstrap** conflict as unresolved. New-run environment provenance does not
retroactively reconcile the old run.

* **Paired backend priorities:** unknown; Mac failed preflight before
  collection. Windows-only profiles cannot rank cross-OS backend gaps.
* **Existing checkout priority:** package checkout-ref and repeated auth
  `foreach` emission windows; fetch differences remain smaller. Underlying
  CPU, filesystem, security software or helper-emulation causes are unknown.
* **Local Trace2:** the parent reported a local no-op child interval around
  2.389s and named helper chain, but its raw evidence is not uploaded and is
  not used here. It is not paired CI evidence or a foundation-cause proof.
* **Screenshot row:** unknown / separate; no screenshot evidence is used or
  substituted with timing metadata.
* **Next paired collection:** requires a working Mac preflight and any
  additional Mac-only run requires new user approval. This audit neither
  requests execution nor launches one.

`metadata-hashes.json` hashes the eight saved inputs actually used:
console, final run metadata, both actual-action receipts, both Python setup
receipts, Windows Git context and Windows diagnostic report (only inventory
metadata extracted; backend profile results not analyzed). Root inputs
remain read-only. Original audit files and its 125-input hash manifest are
untouched.

Confidence **high** in saved-input extraction, like-scope pairing and runtime
receipt interpretation; **moderate** in interval prioritization from one job
pair; **unestablished** in cross-OS backend prioritization, exact auth child
durations, executed helper architecture and causal mechanisms.
