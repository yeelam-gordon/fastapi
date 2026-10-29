# Existing checkout/auth console drilldown

Follow-up to `AUDIT.md`; no new execution measurements. The original 125-input
hash manifest and all original evidence remain unchanged. Structured evidence:
`checkout-command-intervals.json`, sourced only from the retained 75,812-byte
console, SHA256
`00e379f133cb5e6a61cb97f4fe4e550bbafe61abdcba16c58ee960da52834a66`.
Line references below are to that console.

## What is measured, and what is not

An interval begins at the **logged command emission**, not a recorded process
entry event, and ends at the next command emission or explicit action-group
end. These are legitimate **log timestamp intervals**, NOT exact subprocess
durations, CPU times, or allocations exclusively to Git. They may include
Git launch/exit, child processes, Node action orchestration, filesystem and
logging overhead. The structured table records the first intervening logged
noncommand event separately; an action message is not necessarily subprocess
output. No process exit timestamps or exact process durations are supplied.

Post-checkout cleanup has no closing action group here: its final interval
ends at `Cleaning up orphan processes`, explicitly labelled a next-phase
marker, not an observed process end. Nested commands inside a `foreach`
argument are **not** counted as independently emitted processes.

## Exact emitted command counts

Counts are identical on the two runners, within the explicitly selected
setup/removal/checkout and post-checkout ranges:

| Scope | Git config | Git submodule foreach | Git checkout | Git version | Total |
|---|---:|---:|---:|---:|---:|
| Setting up auth | 8 | 3 | 0 | 0 | 11 |
| Checking out ref | 0 | 0 | 1 | 0 | 1 |
| Removing auth within checkout | 11 | 3 | 0 | 0 | 14 |
| Post-checkout cleanup | 4 | 3 | 0 | 1 | 8 |
| **Selected scopes total, per runner** | **23** | **9** | **1** | **1** | **34** |

These are not counts of all processes or all commands in the entire job.
There are **zero explicit Node command emissions in these scopes**; this
does not imply no Node execution. Each auth phase emits three `foreach`
operations, respectively querying/removing SSH configuration, HTTP extra
headers, and querying remote URLs for credential include cleanup. Literal
argv strings and per-command line numbers are retained in the JSON.

## Prioritize absolute gaps, not just Windows duration

The original measured group gaps remain: checkout-ref **5.228505s**,
setup-auth **4.887808s**, removal-auth **4.121539s**. Fetch group gap is only
**0.623956s**. More specifically, the following **disjoint emission windows
inside each auth group** show where the visible elapsed-time differences
concentrate:

| Scope / window class | Windows s | Mac s | Gap s |
|---|---:|---:|---:|
| Setup: three `foreach` windows | 4.753191 | 0.246567 | **4.506624** |
| Removal: three `foreach` windows | 3.788339 | 0.191536 | **3.596803** |
| Setup: eight config windows | 0.428349 | 0.047440 | **0.380909** |
| Removal: eleven config windows | 0.578756 | 0.054670 | **0.524086** |
| Post-cleanup: three `foreach` windows | 3.649315 | 0.220800 | **3.428515** |
| Post-cleanup: four config windows | 0.206548 | 0.023695 | **0.182853** |

Setup+removal's six `foreach` emission windows contain **8.103427s** of
observed paired interval difference, versus **9.009347s** for their enclosing
groups. This localizes an investigation; it is **not** proof that Git
subprocess CPU or shell startup caused that amount of slowdown.
The first Windows setup `foreach` window is **2.293889s**; the other eight
Windows `foreach` windows across the three auth/cleanup scopes are
**1.189126–1.276520s**. Mac's nine are **0.056828–0.101559s**.
The 23 config windows per runner are **0.049186–0.057331s** Windows versus
**0.003707–0.008765s** Mac. Repeated same-command-class windows, not more
emitted commands on Windows, are the visible pattern.

### Checkout-ref progress

Windows command emission line **382** to group-end **468** is **5.642363s**;
first progress output line **383** arrives **1.099297s** after emission.
There are **83** `Updating files` events, ending with
`100% (3390/3390), done.` at line **465**, then branch messages **466–467**.
Those are output/progress milestones, not exact subprocess exit events or
CPU/filesystem cost counters. Mac emission **115** to group-end **118**
is **0.414599s**; first branch output **116** arrives **0.413493s** after
emission, with no `Updating files` progress events. Absence of Mac progress
output does not mean no filesystem work. The group difference can be located
to checkout-associated elapsed time, not decomposed into write, conversion,
scanner, Node or CPU costs from these messages.

## Runtime and image provenance: preserve unknowns

The console proves the emitted Git executable paths and version outputs:
Windows `C:\Program Files\Git\bin\git.exe`, **2.56.0.windows.3**
(335–336, 686–687); Mac `/opt/homebrew/bin/git`, **2.55.0**
(54–55, 265–266). Paths/version strings do **not** prove Git process
architecture. Runner **2.338.0** is printed on both (1, 281), but neither
Actions' actual Node `process.execPath`/`process.arch` nor a PATH Node version
or architecture is printed. The old console therefore **does not establish
Actions Node24 architecture or emulation**. The pinned checkout action
reference alone is not executed-runtime architecture evidence.

Windows console image group **297–300** identifies
`windows-11-vs2026-arm64` / **20261025.196.1**; the bootstrap receipt records
**20261026.197.1**. The console also links the expected source SHA
(369, 375, 470) and run **40814588064** artifact URL (682).
These support run/source association but do not explain why the image
versions differ or prove which metadata source is authoritative.
**Conflict unresolved**; do not silently reconcile it. Mac remains
`macos-15-arm64` / **20260907.0337.1**, consistent with its receipt.

## Bounded next priority and confidence

1. Retain the already observed **checkout-ref** and repeated
   **`submodule foreach` auth/cleanup** intervals as the checkout analysis
   priorities; fetching is a smaller absolute gap. No network test is
   warranted by these intervals alone.
2. In the separately planned inventory, distinguish **the actual Actions
   Node24 executable and `runtime.arch`** from PATH Node, Git and Python
   identities. Preserve Git executable architecture and resolve image
   metadata provenance rather than guessing emulation.
3. Only matched process boundaries/counters can allocate the interval
   between Git/children and Node/action/filesystem space. Existing logs
   cannot do so. No MDE, CPU, filesystem or other causal diagnosis is made.

Confidence **high** in command counts, literal emissions and log-interval
arithmetic; **moderate** in prioritization from this one paired job;
**unknown** exact process durations, runtime architectures, image-conflict
cause and underlying performance mechanism.
