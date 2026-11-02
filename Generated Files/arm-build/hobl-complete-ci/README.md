# Optional paired complete-HOBL cohort

## Optional maintained-runtime cohort

`hobl-paired-runtime` is a new, optional manual question: stock CPython
**3.12.10** versus candidate **3.13.15**, both using the same official native
uv **0.13.6** frontend and isolated PDM **2.5.0** sdist-to-wheel build.
Existing default/frontend modes and their phase clock are unchanged.
No SQL/native overlay, observer, profiling hook, omitted feature or new skip.

Exactly two 20-minute jobs use `windows-11-arm` and **`macos-14` ARM64**.
The latter is the documented standard ARM alternate in GitHub's
[hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
not a paid runner or automatic fallback. Both Mac runtime arms stay on that
same label. Actual OS/hardware/runtime identities are retained; this is not
a matched comparison with earlier macos-15 timings. A new label does not
guarantee capacity. There is no rerun, fallback or runtime-mode pip retry.

Windows stock retains the existing hash-verified PSF 3.12.10 portable archive.
Candidate 3.13.15 on both hosts, and Mac stock 3.12.10, use the same pinned
official setup-python action (`5fda3b95a4ea91299a34e894583c3862153e4b97`),
`architecture: arm64`, `update-environment: false`, explicit action output
paths and separate lexical venv executable paths. **Provisioning, including
Windows action ARM64 availability, remains a runner-only uncertainty**;
unavailability fails, not substitutes another release/architecture.
No invented archive hash or local runtime download is used. Before timing,
installed-payload probes require exact version, ARM64/64-bit, normal GIL,
no JIT, correct source import, native original coverage 7.17.0, compatible
WHEEL ABI tags and exact common package versions. WHEEL/RECORD identities
are retained. The uv executable is bootstrapped once with its distribution
RECORD gate. Platform-only colorama/uvloop pins remain platform-specific;
all within-host runtime-arm pins must match, without optional omissions.

Source is **FastAPI 0.119.1 plus one common test-helper correction**, not the
unpatched tag: `tests/utils.py` changes `> (3, 13)` to `>= (3, 14)`.
Preparation verifies the upstream committed blob, exact known old/new hashes,
patch bytes and a clean source checkout before writing. Original 2557-file
manifest/hash and the corrected manifest are retained: 2556 unchanged files
plus that one declared helper. The patch is `-text` for transport safety.
Both arms must report exactly **2513 passed, 130 skipped** every iteration.

Reuse of the existing schedule gives one excluded complete warmup/runtime,
then five **AB/BA/AB/BA/AB** pairs (10 measured rows/host). Dist remains
available during tests and is moved/audited only after full outcome/source
gates. Windows uses the unchanged coverage pytest command; Mac uses the
canonical `bash scripts/test.sh`, including its `PYTHONPATH=./docs_src` reset.
Arm-owned HOME/config/temp and version-tagged bytecode caches are separate.
Initially empty shared pip/uv dependency caches warm in the fixed order;
identical OS cache warmth is not claimed. Source content is common/frozen.
Only runtime and matching-ABI wheel payloads differ within a host.

Each iteration has a fresh private COVERAGE_FILE. Its **two actual main/CLI
shards** are merged in memory through public CoverageData APIs inside the
installed payload interpreter, never the clean base coordinator. Canonical
source-relative file identities (863), context identities (1409), exclusions,
and every reportable line/context association must agree. Raw oracles,
shards, warnings and all differences survive, including existing excluded
source-branch differences; no runtime-version whitelist. Original
`analysis2` exclusions alone classify differences; reportable loss or any
warning fails. Archive/RECORD/member/mode/source gates remain mandatory.

The worker's existing guardian has a **1100-second** runtime-pair deadline
inside the 20-minute job limit. `phase()` is unchanged. The worker result is
pending until the receipt succeeds with natural drain, no survivors/errors/
timeouts. Arm medians use actual complete build+test row totals, excluding
warmups, not added phase medians. Labels are stock/candidate runtimes, not uv.
Failure evidence is retained, never retried or replaced.

Offline unit/mock/tiny API probes establish local readiness only. Future
actual runner provisioning, full outcomes/oracles and performance remain
unmeasured. Existing local runtime evidence and maintained-uv evidence are
separate, not additive. This mode does not imply Python 3.13 is always faster.

## Existing frontend cohort

The manual workflow's default `hobl-complete` and `hobl-macos` modes retain
their baseline commands and five measured loops. `hobl-paired-uv` selects both
existing ARM hosts, with the same 20-minute job limit and no automatic rerun.

The optional `run_payload.py --paired-uv ABSOLUTE_EXE --loops 5` path uses
the existing phase clock, source, interpreter, identity, test commands, score
sum and process guardian. The stock command remains exactly `python -m build`.
The declared treatment is supported native `uv build --python ...` with
complete isolated sdist then wheel-from-sdist semantics, not wheel-only or
no-isolation. Both isolated backends are constrained to pdm-backend 2.5.0;
every wheel must attest `Generator: pdm-backend (2.5.0)`.
The stock arm copies the exact constraints bytes into its owned output and passes
that file's percent-encoded `file:` URI through `PIP_CONSTRAINT`. pip splits
environment constraint lists on whitespace (shell quoting does not protect
spaces); the URI preserves helper/output paths containing spaces without
changing the build command. The effective URI and original constraints hash
are retained in `paired-config.json`.

Preparation installs official `uv==0.13.6` through normal pip/index settings,
only in paired mode. `prepare_uv.py` resolves its bundled executable with
`uv.find_uv_bin()`, checks ARM64 PE/Mach-O identity and version, and records
its absolute path and SHA256. No persistent PATH change or extra action.
Its executable hash must also match the installed distribution's RECORD;
the module's global/user fallback paths are not accepted as bundled provenance.
The extra package is common to both arms of this **new** cohort; previous
baseline jobs are reference observations, not matched controls.

One complete stock warmup and one complete uv warmup precede five measured
within-host pairs: **AB / BA / AB / BA / AB**. All twelve rows and their raw
logs survive; only the ten measured rows enter per-arm medians. A complete
score is each iteration's actual build wall plus actual full covered-test
wall, not the sum of separate phase medians. Every warmup and measured row
requires exactly **2513 passed, 130 skipped**, exit zero and all 2557 canonical
source hashes unchanged.

Both arms share the same source, bytecode, runtime closure, home and scratch.
Initially empty pip and uv dependency caches are separately tool-owned and
warmed by their respective complete warmups. Source/test bytecode and OS cache
then evolve naturally in the fixed order; identical OS warmth is not claimed.
No tests, coverage configuration, plugins or skips are changed. There is no
observer. Tool/bootstrap work is outside phase timing.

Each iteration retains complete sdist/wheel bytes under its own artifact
directory. All member names, uncompressed content hashes, modes/types and
RECORD entries compare against the first stock archive set on that host.
Raw timestamp/compression identity is not required. Source payload ties are
checked; generated sdist pyproject TOML may only freeze the version and clear
the dynamic version list, while all generated bytes must still agree between
arms. Cross-host byte/mode identity is not assumed.

The existing guardian owns the entire worker/descendant tree, with a bounded
1000-second paired deadline. Successful scoring also requires its established
ownership, zero exit, natural drain, no survivors, complete cleanup and no
errors. An unsuccessful final receipt invalidates a prepared result. Failures
are retained and never retried/substituted.

Identity also records safe logical CPU count, OS/release and available
processor description before timing. Missing model information is explicit;
logical CPUs do not establish physical-core counts or matched hardware.

Local tests use tiny mocked complete workloads and tiny real archives, not a
local full-suite/performance cohort. Actual runner provisioning, outcomes,
archive equality and complete timings remain mandatory gates. No local
readiness result establishes a whole-HOBL speedup or Windows/Mac parity.

## Optional matched native-context trial

`native_context_inputs.py --source OWNER_TREE --output NEW_OWNED_DIRECTORY`
is an offline, non-executing source gate. It copies 59 pinned source/license
inputs into separate stock/candidate trees, preserving original bytes and
per-file newline conventions. It verifies all four patched results and writes
the complete input manifests and transport hashes into `source-receipt.json`.
No installed coverage package or existing binary is modified or copied.
No compiler, source downloader, package installer or workflow is invoked.

Owner: coverage.py 7.17.0, coveragepy/coveragepy commit
`393ac715ddae841a85452d97edeedd8be8f0cda8`.
The manifest derives from the retained original official source and the
already-reviewed normal-GIL 3.13 candidate, not an installed wheel's C files.
`native-context.patch` is the unchanged 35-addition/one-removal experimental
four-file treatment; exact raw patch SHA256 is checked before interpreting
line endings. `native-context-LICENSE.txt` and `native-context-NOTICE.txt`
retain the owner's Apache-2.0 license, Ned Batchelder attribution and notices.
No whole third-party package or compiled extension is included in git.

`hobl-paired-native-context` selects Windows11 ARM and macOS14 ARM, with
normal-GIL/no-JIT Python3.13.15 in BOTH lexical venvs, common80 package pins
and uv0.13.6/PDM2.5.0. Default and runtime-comparison modes are unchanged.
Native preparation fetches only the pinned GitHub commit with normal TLS,
checks every source input, builds two extensions with one installed compiler,
and creates owned package overlays without changing either installed wheel.
Preparation has a90-second strict-owned outer bound, each child at most180
seconds; the existing unmodified guardian must accept every receipt and
natural drain. The paired worker keeps its1100-second bound, job20minutes.
Missing LLVM/Xcode/SDK/native headers or exhausted capacity fails closed,
without compiler downloads, retries, telemetry flags or cleanup exemptions.

Reuse recipe: the retained `epoch8-py313/BUILD-SPEC.json` compiles exactly
`datastack.c`, `filedisp.c`, `module.c`, `tracer.c`.
Windows uses supported installed clang-cl/lld-link, ARM64 output,
`/O2 /MD /std:c11 /W3`, no `/GL`, LTO or PGO. Read-only bounded VS/MSVC
and Windows Kits discovery selects one coherent SDK include/library version.
Explicit `/imsvc` and `/LIBPATH:` paths configure compilation/linking;
no vcvars, VS setup, vswhere or compiler-discovery helper is executed.
Only standard Windows Kits HKLM install-root metadata may be read.
Mac requires installed Xcode clang and native 3.13 headers, with
`-O2 -std=c11 -fPIC -shared -undefined dynamic_lookup -arch arm64`,
not Windows flags. Neither compiler may be downloaded automatically.
Headers/library/suffix paths must come from the actual payload's sysconfig;
the lexical venv executable must not be resolved to a clean base interpreter.
Normal-GIL/no-JIT assertions remain mandatory before compilation and timing.

Before timing, three tiny default/surrogate, callback-mutation and raising
audit cases compare the official wheel, compiled stock and compiled guard.
Source, installed packages and overlays/binaries are sealed before/after.
Mac keeps the original script; a common BASH_ENV coverage function reapplies
only the arm's owned overlay at the CLI boundary after the script resets
PYTHONPATH. Args and docs_src remain intact, including CLI-child imports.
Both arms keep two excluded complete warmups and five AB/BA pairs, exact
2513pass/130skip outcomes, two fresh shards and original reportable-context
and archive gates. Results remain pending until the final owned receipt;
the screen passes only with >=1% complete-median decrease, all five pair
savings positive and both order groups positive. A valid negative is retained.
All source, compiler argv/version/host identity, binary hashes and ABI
receipts, semantics and raw shards/archives are uploaded for review.
Hosted compilation and the actual full paired pipeline remain unexecuted
local-readiness gates; fresh parent review is required before dispatch.
Earlier SDK-script probes failed the strict guardian and remain retained.
The explicit-path recipe subsequently built both fresh extensions and passed
ABI/import and three-arm tiny semantics under the same unchanged guardian.
This is build-only local readiness, not a full80-pin HOBL replay or hosted proof.
No telemetry/protection switch or lifecycle exception is added.
Configuration references: [Microsoft Clang support](https://learn.microsoft.com/en-us/cpp/build/clang-support-msbuild)
and [Microsoft /LIBPATH](https://learn.microsoft.com/en-us/cpp/build/reference/libpath-additional-libpath);
the installed clang-cl/lld-link help documents `/imsvc` and `/libpath:`.

The accepted 79.5979381s to 78.1468361s local matched-LLVM screen (1.823%)
does not answer transfer to hosted Windows LLVM or Mac Xcode. The official
PGO wheel is only a semantic reference. Other-platform/free-threaded owner
acceptance, maintained Windows/Mac parity and released-package gains remain
open; this source gate supplies no performance result.
