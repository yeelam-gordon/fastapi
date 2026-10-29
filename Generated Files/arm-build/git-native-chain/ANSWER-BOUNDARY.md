# ARM64 Git: verified boundary

**Not an all-x64 Git installation; not a generally slow-Git conclusion.**

| Scope | Established evidence | Missing proof |
|---|---|---|
| Current CI entrypoint | Selected Git entry file is ARM64; its header/hash/path are retained | The CI descendant image chain was not sampled |
| Local actual Git body | Observed `clangarm64\bin\git.exe` executing, ARM64 image | Local VFS build differs from the CI distribution |
| Local shell path | Observed `usr\bin\sh.exe`, basename/sed/uname x64 images in the owned command chain | No instruction-level or CPU-cost attribution |
| Installed CI shell | Shell and submodule-script hashes match the executed local shell/script bytes | A content match is not proof that CI executed that path |
| Public packaging | Native clangarm64 Git coexists with x64 MSYS tools; shell wrappers delegate | Does not quantify interpreter/emulation/filesystem/antivirus shares |

The no-op local traversal sampled 43 process instances and eight images.
That is not a sum of process CPU or elapsed time and is not a matched Mac
measurement. Raw `IsWow64Process2` UNKNOWN results are retained; they are not
reinterpreted as affirmative native-image results.

The specific investigation target is repeated shell/setup work around
`git submodule foreach`, especially generic credential cleanup. It is not
all Git commands. Neither full-history download nor MDE is an established
cause. Avoid private internal-helper shortcuts or ignoring stale credentials.

Public source explanation: `..\git-public-research\PUBLIC-RESEARCH.md`.
Enterprise MCP results remain local/ignored; only public corroboration appears
in these public reports. WorkIQ returned technical references; direct ADO
connections failed, so no ADO-derived claim is made.
