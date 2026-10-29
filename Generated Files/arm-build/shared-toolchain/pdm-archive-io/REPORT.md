# P23 — official PDM sdist I/O: source-only feasibility

**Verdict: no-go for implementation/adoption now (high confidence).** There is
an authentic serial-open/read overlap opportunity, but no demonstrated tiny,
generic PDM metadata fix or maintainable byte-bounded prefetch implementation.
Keep prefetch as a conditional research candidate, not another SDK or campaign.
No builds, benchmarks, installations, production edits, CI, owner contact or
foreign code execution were performed. Public Python files were read, not imported.

Scope follows [GOALS](../../../GOALS.md), [PERSONA](../../../PERSONA.md) and the
[ranked table](../../../INVESTIGATION-AND-PROPOSALS.md): shared-toolchain value
first; portable existing practice second; bespoke/private patches rejected.
Maintainer acceptance is mandatory. Source identity and hashes are in
[PROVENANCE.md](PROVENANCE.md). PDM 2.5.0 resolves to official commit
`8c6653726f71afdb2059b44dc9c7706693e95be6`; this is not a claim about latest PDM.

## What the standard path actually does

* [Public build_sdist entrypoint, lines 61–68][entry] creates `SdistBuilder`.
  [Builder, lines 184–224][lifecycle] cleans as configured, initializes hooks,
  collects files, lets update-files hooks change that map, collects build-dir
  outputs, sorts the final pairs, writes the artifact and finalizes. Selection
  is PDM's, not a FastAPI list.
* [Collection, lines 234–269][collect] tests `Path.is_file()` and stores **paths**,
  not stat results. Those tests precede update-files hooks. [Sdist selection,
  lines 58–96][selection] validates metadata, adds custom hook/readme/license
  inputs including external paths, rewrites references and generates pyproject.
  [Dynamic version initialization, lines 31–71][dynamic] resolves supported
  file/SCM/call sources. None may be replaced by cached project metadata.
* [Archive loop, lines 98–125][archive] opens one `w:gz`, PAX tar, then serially
  calls `gettarinfo(path)`, cleans metadata, opens only regular members, streams
  them into `addfile`, closes the input and logs it. Nonregular members are added
  without payload opens. Fresh RFC822 `PKG-INFO` is appended last.
* In the pinned CPython reference, [gettarinfo, lines 2169–2236][tarstat] uses
  `lstat` by default, records hardlink identity and symlink targets, and builds
  size/mode/time/type metadata. [addfile, lines 2333–2361][taradd] copies the header
  and exactly the advertised payload length; [copyfileobj, lines 237–259][copy]
  uses bounded chunks (default 16 KiB) and errors on premature EOF. There is not
  a second pathname stat in this PDM archive loop to trivially delete.
* [clean_tarinfo, lines 21–40][clean] copies the TarInfo, clears ownership names
  and IDs, normalizes permissions and optionally sets `SOURCE_DATE_EPOCH`.
  Keep that policy, link behavior, member order, logging and stdlib writer.
  [TarFile.gzopen, lines 1991–2005][gzopen] defaults to gzip level 9 on this runtime;
  [gzip, lines 185–194][gzip] also documents time-dependent headers. Do not change
  codec, compression level or container timestamp policy to manufacture a gain.

## Historical attribution, not new measurements

| Retained evidence | What it supports / does not support |
|---|---|
| [profile-01/sdist.txt](../../results/profile-01/sdist.txt), [receipt](../../results/profile-01/profile.json) | PDM 2.5.0 diagnostic: sdist 1.659 s, archive loop 1.270 s cumulative; `_io.open` 0.312 s self, `nt.lstat` 0.106 s, `nt.stat` 0.074 s, buffered reads 0.080 s, compression 0.221 s. Nested cumulative times overlap; these are not additive savings or full frontend timings. |
| [C/Q follow-up](../../filesystem/c-vs-q/followup/REPORT.txt), [profile](../../filesystem/c-vs-q/followup/PROFILE-top40.txt) | Separately profiled corrected writer: 2.3381 s sdist, open self 0.9445 s, lstat 0.1476 s, stat 0.0905 s, reads 0.0881 s. The earlier 7.129 s C sdist stall did not recur; do not retrospectively assign its missing seconds to selection or Defender. |
| [stdlib-ops](../../filesystem/stdlib-ops/REPORT.txt), [mechanism](../../filesystem/stdlib-ops/ops.py) | Three paired warm trials with attributes held constant: sequential-to-threaded wall medians 3.3031 → 2.4257 s; paired saving median 0.8586 s; sdist medians 1.9695 → 1.1229 s. Both used whole-file buffering, private PDM overrides, canonical modes and selective extraction. This isolates useful overlap within that diagnostic, **not** a stock-command upstream speedup. |
| [SDK profile](../../profiles/sdk-validation/README.md) | Its 10,578 safety-walk stat calls and ~0.524 s prefix belong to the rejected wrapper, not official PDM. Calling-thread cProfile also misses reader-thread attribution. Do not transplant this walk optimization or subtract unpaired timings as a PDM gain. |

The stdlib diagnostic reported 1,286 sdist `open` audit events in every cell:
overlap did not eliminate opens. Three futures limit task count, **not bytes**:
`read_bytes()` can retain roughly four whole payloads and has no generic large-file
bound. Its length-equality guard also differs from stdlib's exact-size copying.
Audit events are not kernel operations or antivirus scan counts. Filesystem
location, warm caches, interpreter and extraction strategy confound comparisons;
[METHOD](../../filesystem/METHOD.md) records the tracing boundary. No new
standard-command, multi-project, memory, cold-cache or Mac measurements exist here.

## Ranked feasibility (priority is not approval)

| Rank / owner | Change point / generality | Benefit evidence / unknowns | Compatibility / maintenance / decision |
|---|---|---|---|
| 1 — PDM; simpler metadata reuse **before threads** | Reuse already-acquired stat at the archive boundary, if one exists; potentially all layouts | Current FileMap retains no rich stat. Selection's earlier following-link classification is not archive `lstat`, and hooks can replace paths. No removable same-boundary duplicate demonstrated. | Carrying stale selection stats through hooks is unsafe; changing FileMap/hook contracts or cloning tarfile metadata logic is disproportionate. **No-go; high** on absence of a local reuse opportunity in this source. |
| 2 — PDM; bounded read overlap | Only final selected archive inputs in `SdistBuilder.build_artifact`; no new selector or metadata producer | Serial loop and diagnostic overlap benefit are real. Standard-command benefit, small-project overhead and large-file memory remain unmeasured. | A possible generic design must retain serial tar state/writes, byte reservations and large-file streaming fallback; thread/error lifecycle adds real review cost. **Research-only; medium** that overlap merits consideration, **low** that value justifies adoption. |
| 3 — PDM; open-first `gettarinfo(fileobj=f)` | Public stdlib fstat alternative; superficially small | Still one metadata call and one open per regular file; no measured saving. | Blind opening follows symlinks, opens otherwise metadata-only hardlinks, and can fail/block on directories/FIFOs supplied by hooks. Classifying first reintroduces metadata work. **Reject as a generic drop-in; high.** |
| 4 — CPython, not a private PDM patch | Avoid owner-name lookups whose results PDM discards; generic tar metadata-policy API would have wider scope | [gettarinfo 2221–2230][owners] resolves pwd/grp when available; Windows has no ordinary Unix pwd/grp benefit. No measured relevant cost. | No existing skip switch here; global module patching or duplicating gettarinfo is unacceptable. A new stdlib API needs independent evidence and ownership. **Out of this small PDM proposal; high** on mismatch, **low** on useful benefit. |
| 5 — FastAPI portable practice | Existing supported uv/native ARM/pinned reproducible inputs | Already used; not a new improvement from P23 | Keep supported practice; no repository optimization justified here. All selector/manifest/private-SDK/custom-writer adoption routes remain **rejected (high)**, not lower-ranked fallback work. |

### Why prefetch is not yet a small upstream proposal

Any later minimal experiment must keep PDM's final sorted selection and hook
lifecycle unchanged. TarInfo generation/hardlink bookkeeping and tar/gzip writes
must remain serial. Only bounded regular payloads may be read ahead; a total
byte budget must include the current buffer, pending results and in-flight reads,
not merely cap workers. Do not trust `read_bytes()` or file size alone to bound a
file that grows. Oversized files must use existing streaming without starvation.
Preserve advertised-size copying, short-read errors, zero-size files and
metadata-only links; do not import the prototype's new equality rule.

Read failures must surface at the appropriate archive member rather than through
completion-order iteration. Earlier metadata acquisition can itself change
error/partial-output sequencing and needs scrutiny. Reader handles must be closed
inside tasks; completion, failure and early writer exit must cancel unstarted work
and join running work before return. No live handles, hidden worker exceptions or
background reads after failure are acceptable. These are requirements to prove,
not a validated design; no new setting, framework or implementation is proposed.

## Compatibility is upstream behavior, not our special oracle

Official [permission normalization, lines 166–178][modes] derives executable bits
from filesystem mode. It does **not** consult a Git/canonical mode inventory.
Historical real uv builds lost five 0755 script modes on Windows relative to the
Mac reference, while payload/RECORD checks passed; that remains a recorded strict
oracle failure. An I/O-only candidate must match **unchanged upstream behavior on
each host**, not silently inject Git mode restoration to make the special oracle
pass. Portable executable-mode handling is a separate correctness issue requiring
its own owner, specification and tests; no waiver and no combined feature here.

## Small later discriminating gate — not authorization to run it

1. Extend existing [API layout tests][apitests], not a new harness: flat module,
   flat package and src package, explicit includes/excludes/source-includes,
   license/readme external paths and generated pyproject; preserve all members,
   payloads, PAX metadata and order.
2. Extend [hook tests][hooktests] with an sdist update-files hook that adds,
   removes and replaces paths plus a generated build-dir file; retain initialization,
   dynamic version, fresh `PKG-INFO` and finalize behavior.
3. Focused archive cases: empty file, boundary-sized and oversized file streamed
   under a measured byte bound, symlink/hardlink where supported, missing input,
   premature EOF, early writer error and cleanup. Check source handles/workers
   are gone on both success and failure. Do not demand identical gzip bytes when
   upstream deliberately uses wall-clock header timestamps.
4. Only if a small patch survives those tests: repeated alternating fresh-process
   **full standard `uv build` sdist→wheel commands**, official pinned backend
   versus proposed upstream backend in otherwise identical environments. Include
   imports/thread startup/shutdown/frontend overhead, fresh outputs, normal
   selection/hooks and full extraction; no SDK/private adapter. Measure small,
   many-small-file and large-file projects, peak memory, medians/ranges and artifact
   semantics; record setup separately and isolation/cache policy explicitly.
   Apply the same candidate to contemporary native ARM Windows **and Mac**.
   No parity inference or optimizing against the old Mac time.

**Maintainer rationale:** Reject a PDM performance change today because the
available speed evidence is attached to a non-adoptable diagnostic pipeline,
while the official loop already streams with bounded memory and has no obvious
redundant local metadata fetch. Carrying pre-hook stat state, opening every file
first, or copying tarfile internals would trade correctness and review effort for
unmeasured value. A narrowly bounded, ordinary-file read-ahead patch could belong
in PDM for all projects only after the small tests and full-command comparison
above show material benefit without regressions or a substantial lifecycle/API
burden. This is a concrete source-only no-go, not a claim that parallel I/O cannot
help Windows, Mac, or packaging generally.

[entry]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/src/pdm/backend/__init__.py#L61-L68
[lifecycle]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/src/pdm/backend/base.py#L184-L224
[collect]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/src/pdm/backend/base.py#L234-L269
[selection]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/src/pdm/backend/sdist.py#L58-L96
[dynamic]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/src/pdm/backend/hooks/version/__init__.py#L31-L71
[archive]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/src/pdm/backend/sdist.py#L98-L125
[clean]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/src/pdm/backend/sdist.py#L21-L40
[modes]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/src/pdm/backend/utils.py#L166-L178
[tarstat]: https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/tarfile.py#L2169-L2236
[owners]: https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/tarfile.py#L2221-L2230
[taradd]: https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/tarfile.py#L2333-L2361
[copy]: https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/tarfile.py#L237-L259
[gzopen]: https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/tarfile.py#L1991-L2005
[gzip]: https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/gzip.py#L185-L194
[apitests]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/tests/test_api.py#L28-L158
[hooktests]: https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/tests/test_hooks.py#L17-L49
