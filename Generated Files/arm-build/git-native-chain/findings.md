# Git runtime-chain evidence, 2026-10-29

## High confidence: what actually ran locally

One read-only command executed against the source worktree:

```text
C:\Program Files\Git\cmd\git.EXE -C Q:\fastapi\Generated Files\worktrees\source-fastapi submodule foreach --recursive "exit 0"
```

Exit 0; stdout/stderr empty; no timeout, query failures, or process termination.
Elapsed 1.750355 seconds is diagnostic on a shared host, not a performance result.
43 owned processes and eight unique executable images were sampled.

The actual observed parent chain starts:

| PID | Parent | Actual executable | PE machine |
|---|---|---|---|
| 12812 | 10692 (probe) | `C:\Program Files\Git\cmd\git.exe` | ARM64 `0xaa64` |
| 18716 | 12812 | `C:\Program Files\Git\clangarm64\bin\git.exe` | ARM64 `0xaa64` |
| 4804 | 18716 | `C:\Program Files\Git\usr\bin\sh.exe` | x86-64 `0x8664` |

Thus the real ARM64 Git body, not merely its launcher, was observed executing.
Further observed ARM64 images were `clangarm64\libexec\git-core\git.exe`
(same SHA-256 as the main body) and `git-sh-i18n--envsubst.exe`.
Further observed x86-64 images were `usr\bin\basename.exe`, `sed.exe`, and
`uname.exe`. These are **executed images**, unlike installation-path candidates.
The installed `git-submodule` shell script is not itself a PE process image.
No claim is made that `bin\sh.exe` or `bin\bash.exe` executed in this probe.

Every successful live `IsWow64Process2` query returned process-machine
`0x0000` and native-machine `0xaa64`, including the x86-64 shell/utilities.
These raw results are preserved, not converted to fabricated `0x8664` results.
`0x0000` is `IMAGE_FILE_MACHINE_UNKNOWN` (not a WOW64 process), **not proof
that an image is ARM64-native**. In particular it must not override the
observed shell's x86-64 PE header.

## Medium confidence: architecture interpretation and CI applicability

The observed ARM64 Git images on an ARM64 host support native ARM64 Git
execution locally. The observed x86-64 shell/utilities on that host support
the x64-emulation classification locally. Neither statement is a complete
CPU-instruction-family trace: no instruction sampling, DLL architecture
inventory, emulation-engine trace, or hybrid-module inspection was performed.
The API alone did not positively identify x64 emulation.

The actual CI receipt is copied in `ci-git-receipt.json`, extracted from run
40859922266, `platform_inventory.tools.git`; its full report hash is retained
in `result.json`. CI's selected `bin\git.exe` was an ARM64 42,696-byte shim,
SHA-256 `8610a0786aaa02b92655a052e6b99caf386709a3746ae243668a6d8260f49fbd`.
Local PATH instead selected `cmd\git.exe`, a 39,288-byte ARM64 shim:
`d778d40470c57b6b1a0de2f6b18bfb1a1c1ac4782ef14a27fb57de10295399a3`.
Local static `bin\git.exe` has that same local hash, **not** CI's shim hash.
The existing local Trace2 version is `2.56.0.vfs.0.2`, while CI reports
`git version 2.56.0.windows.3`; this is not an exact Git-distribution match.
The local version comes from the earlier trace, not another executed command.
CI did not inventory the real body hash, so no exact body match is established.

There **are** exact local/CI content matches:

* Executed local `usr\bin\sh.exe`: 2,449,886 bytes, x86-64,
  SHA-256 `5490d0da5e7cf9d92068cc48fcc590f2bcf8564add8ff91c3b5fe541eb2d72e3`.
  This matches CI's installed `usr\bin\sh.exe` and `usr\bin\bash.exe`.
* Installed local `git-submodule` script: 10,493 bytes,
  SHA-256 `55a1a450b48fb98cc8c3f5745c411e3391ac7659f46eb4b7eef9053aa3614353`,
  matches CI's script with `#!/bin/sh`.
* Local static `bin\sh.exe`/`bin\bash.exe` hashes differ from CI's ARM64 shims.

Those matches make the same x86-64 MSYS shell path plausible in CI, but do
not prove CI selected or executed it. CI's helper receipt explicitly says
`candidate/not-proven-executed`. No Python or Actions Node architecture is
used to infer Git architecture.

## Low confidence / missing proof

The CI chain's actual body, shell, and utility executions remain unproven:
the receipt contains headers and candidates, not an owned live descendant
chain with process architecture queries. Local evidence cannot fill that gap.
This did not authorize or trigger another CI run, change pinned CI, build C,
or make a performance, Defender/MDE, or general Windows-quality claim.
Mac profiling failed unit preflight; there is no paired backend-cause result.

## Method and receipt limits

`probe.py` is the exact script used for the single dynamic command.
Native Python 3.13.15 and existing psutil 7.2.2 were used.
A private unnamed Windows job was assigned while the root was suspended,
then resumed; querying that job discovers **only owned PIDs**, without
global process enumeration. No job kill-on-close policy was set.
Query-limited handles supplied creation FILETIMEs, parent PIDs, and
`IsWow64Process2` results. psutil fetched executable paths for those PIDs only.
Polling at a requested 5 ms interval is **partial sampling**: short-lived
processes may be missed, and no completeness claim is made. Paths are PID-based
queries adjacent to the handle queries, not an atomic kernel event receipt.
Unique-image headers, sizes, and hashes were read after command completion;
they identify the installed file at that time, not an immutable loaded-image
snapshot. A hypothetical replacement between sampling and hashing is not excluded.
No other process arguments, environment, global process lists, system tracing,
network/auth operations, security settings, or source changes were requested.
The command has a 15-second loop bound and owned-handle cleanup if needed;
the normal observed run used no termination.

`result.json` retains every sampled process's PID, parent PID, creation time,
first/last observation, actual executable path, and raw live API codes, plus
per-image headers/hashes and CI comparisons. `stdout.txt`/`stderr.txt` are raw
command output. `existing-trace-public-extract.json` preserves only public
Git version/child-exit fields from the pre-existing trace; its original hash
is in `result.json`. Original root receipts were not changed.
`local-ci-static-comparison.json` explicitly labels non-executed candidates.

Validate saved receipts (does **not** execute Git):

```powershell
& 'Q:\fastapi\Generated Files\arm-build\tools\official-tool-environment\Scripts\python.exe' -B '.\Generated Files\arm-build\git-native-chain\validate.py'
```

API semantics: [Microsoft IsWow64Process2 documentation](https://learn.microsoft.com/en-us/windows/win32/api/wow64apiset/nf-wow64apiset-iswow64process2)
(read 2026-10-29): process-machine UNKNOWN means not WOW64; native-machine
identifies the host architecture.
