# P50 native hardware-family control: source integrated, not allocated

Base: exact public `0391ca65a937e77f7a5ae54fb99306631ccb8d54`.
Local branch: `perf/arm-cobalt-control`. No commits, pushes or dispatches.
The parent authorized source integration and one untimed Windows proof only.

## Entry point and finite future contract

The existing registered manual `arm-build-experiment.yml` now describes exactly
two jobs: `windows-11-arm` and `ubuntu-24.04-arm`, contents-read permission,
pinned existing actions, exact fork/ref/manual-attempt-1 guards, 20-minute job
ceilings and three-day evidence retention. No Mac, analysis, aggregation, push
trigger, default-branch or unrelated workflow-state changes.

`control.py` reuses P40's pure source, hash, native ABI, command, full archive/
RECORD and within-host comparator functions. It does **not** instantiate
`FrontendRun`, use its AB schedule or its old hosted ref guard. The only build
command is pinned native uv's default full sdist-then-wheel-from-that-sdist.
No observer, hook, profiler, backend patch or source-scope reduction is active.

Before any build: actual CPU/core attestation, native interpreter/uv/ABI/
source-prefix guards, security/resource child proof and an owned native
process lifecycle preflight must pass. CPU ambiguity fails before the warmup.
Then exactly **one excluded full warmup**, which must pass all correctness/
artifact gates, followed by **six single-stock samples**. No extra correctness
build, separate hash-probe build, A frontend, retries or 5% winner rule.

The full source is raw-LF FastAPI 0.119.1 revision
`864b569cf8453654fc3bc2c64108c0f644e2918c`, all 2,557 Git blobs, canonical
`git archive --format=tar.gz` SHA256
`4cba86b9b9d61883fe786425a505149ca777782cfe266e274796097c30eb8e83`.
Stock PDM 2.5.0 wheel:
`5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63`.
Singleton wheelhouse, absolute file-URL hashed constraints, offline/no-index/
no-config/no-managed-download selectors and SDE `1700000000` are unchanged.
Fresh complete source per command; the same new private uv cache is warmed by
the excluded warmup and retained for all six samples. HOME, config, temp and
other caches are private. Default backend bytecode is retained.

All 1,196 sdist and 58 wheel members are inventoried; RECORD and original
source bytes/mtime/modes are checked outside timing. The ordinary stock
`.pdm-build` metadata is checked semantically; its marker retains the actual
platform newline. The exact normal `pdm_build.cpython-312.pyc` header, code
and filename are verified using the portable P47 proof, without executing it
in the validator. Unknown extra source files fail. Every sample must also
match the warmup using the existing full raw within-host comparator.

## Ownership and the native clock

Reuse `protocol/owned_process.py`: existing Windows Jobs and POSIX
`start_new_session`/owned-group cleanup. No new ownership framework.
The small optional `native_clock` extension records `perf_counter_ns`
immediately before the supervisor directly spawns uv and, in the controller,
after the supervisor has exited and the owned family is confirmed drained.
Both platforms use this **same boundary**. Supervisor startup/initialization
is excluded on both, never charged only to Windows. Supervisor result-return/
shutdown and family drain are included on both; this is not claimed to be an
instruction-level uv-only exit clock. Both integer endpoints are retained.
All source, input, filesystem, artifact and RECORD work is outside it.
Failed ownership, leftover descendants, bad clocks or cleanup fail the sample.

The supervisor uses `-B` only for itself, not an inherited bytecode-disabling
environment variable. The public uv command and its backends retain default
bytecode. Windows explicitly propagates `NoDefaultCurrentDirectoryInExePath=1`
to every pipeline child. Existing selected certificate/security settings are
preserved; an actual child fingerprint verifies them without dumping values.

For CI, exactly four guest cores/logical CPUs and four usable CPUs must be
actually attested. That guest boundary bounds all descendants; uv concurrency
flags alone are not substituted for it. The local Windows-only exception
uses the existing current-process affinity method before children and records
the real larger guest, never marking it a comparable four-core cohort.

## Hardware and filesystem scope

Microsoft's primary [Cobalt overview](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/cobalt-overview)
maps Cobalt 100 to the Neoverse N2 design. Every new host must independently
report a compatible actual model, Arm implementer `0x41`, part `0xd49`, and
exactly four guest/usable cores. Windows additionally requires Cobalt 100,
ARM64 CIM architecture and its D49 identifier; actual per-CPU registry MIDR
fields supply implementer/part. Linux uses per-CPU `/proc/cpuinfo`, actual
`lscpu` model/topology, online count and process affinity. Missing, mixed,
masked or mismatched metadata aborts; neither a label nor an ELF header
attests CPU-family comparability or Microsoft SKU identity.

Each actual workspace, source, temp, cache, HOME and runtime path gets its own
resolved filesystem/mount/capacity receipt. Windows resolves volume mount
paths rather than assuming every C: path is the same volume. No cloud
metadata, credential/serial/private-ID queries, admin, trust or security
policy changes.

Even a passing new cohort controls family/guest cores only. Compiler/runtime,
libc, storage, filesystem, virtualization and security remain joint-stack
differences. This is not pure OS causality, an old-Mac comparison, a Linux/WSL
replacement for Windows or a native-Windows improvement. No pooled historical
ratio. Six new samples are descriptive only.

Cross-host executable script modes and ZIP creator/header provenance remain
**UNWAIVED**, including the five previously identified scripts. The retained
full inventories permit payload-semantic comparison, not invented raw
cross-OS identity. Within-host validity does not close that cross-host gap.

## Exact Linux distribution

`linux_bootstrap.py` requires already-running native AArch64 Linux and uses
normal TLS and complete archive hashes before native tar data-filter
extraction. It verifies executable hashes and ELF64 little-endian machine
183 before executing the selected runtime.

* uv 0.13.6 GNU AArch64 archive:
  `https://github.com/astral-sh/uv/releases/download/0.13.6/uv-aarch64-unknown-linux-gnu.tar.gz`
  SHA256 `229e194255c7958d86d56e8790d969a6f74736592133f0dfd0076f754c642c1d`;
  executable `7d60258dc76bca41d7b3591cdd829fa9633827fad944970bf5e1fb2a8c01476d`.
* Standard, non-debug CPython:
  `https://github.com/astral-sh/python-build-standalone/releases/download/20250529/cpython-3.12.10%2B20250529-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz`
  SHA256 `235d0666528a8e948896f68c08964dc8dd14a54c68e5cbd4924594d2e20f81b9`;
  `python/bin/python3.12` executable
  `5d66d5cf068a0303d145a34c9aa22e226a0f23ba7e0e9e573325b18002437313`.

Python is pinned by uv source
`329bf9448afd9f9088d14a4d57fbc61eb454f117`,
`crates/uv-python-managed/download-metadata.json`,
key `cpython-3.12.10-linux-aarch64-gnu`; not floating latest.
The Linux actual-runtime receipt captures compiler, libc and sysconfig
configuration. Static metadata shows GCC cross-build and LTO; a generic
PGO variable does not establish active/trained PGO. Windows retains the
unchanged official stock Python ZIP/executable/DLL and uv hashes, not P47's
patched runtime.

## Verified locally; genuine remaining limits

Source integration passed 66 portable/policy tests (one existing opt-in test
skipped), all 17 existing/extended ownership tests, absolute existing Ruff
check/format, actionlint, exact PowerShell AST/Git Bash syntax, and diff checks.
One actual **untimed** Windows stock-native full correctness build completed:
all 2,557 source inputs and 1,196/58 full artifacts/RECORD passed, raw outputs
matched the retained Windows stock reference within its original gzip-mtime
allowance, no survivors, cleanup complete, default bytecode/source-cache
provenance valid. Actual guest: **Cobalt 100, 16 cores/logical CPUs**, own
affinity mask `15` (four usable CPUs). It is **not** a four-guest-core
measurement; measured sample count is zero.

That proof used a new private copy of the exact official stock runtime to
avoid old-runtime writes. Original runtime file hashes were unchanged.
The proof's actual helper/ownership/workflow closure is frozen in parent
evidence; no further source execution is needed to call it an untimed proof.
Final static review subsequently added only raw source/dist artifact upload
paths for failures. The workflow-only hash revision is recorded separately;
all 11 executed helper hashes still match the proof. Its original 22-input
snapshot is preserved, not rewritten to claim the workflow was unchanged.

No running local Linux distro was reported by the initial bounded query;
nothing was installed or started. Linux ELF/archive bytes were statically
verified, but Linux extraction/bootstrap, actual runtime ABI/libc, topology/
mount tools, process-group lifecycle and full UV correctness remain
**NATIVELY UNEXERCISED**. A future host must pass bootstrap/identity/ABI and
lifecycle gates before the full correctness warmup, and validate that warmup
before any sample; fixtures do not substitute for them.

Confidence: **high** local Windows correctness/source closure; **medium**
conditional Linux source readiness; **low** any performance or four-core
comparability conclusion until genuine new-host receipts exist.

Parent evidence:
`Generated Files\arm-build\runner-hardware-control\readiness\SOURCE-INTEGRATION.md`.
The registered workflow path is available, but this branch is local and
unpublished. No allocation/publication is authorized by this source work.
