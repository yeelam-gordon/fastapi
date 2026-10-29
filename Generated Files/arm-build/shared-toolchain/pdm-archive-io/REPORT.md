# P23 — official PDM sdist I/O: source-only feasibility

**Initial source-only verdict: no-go for implementation/adoption (high confidence).** There is
an authentic serial-open/read overlap opportunity, but no demonstrated tiny,
generic PDM metadata fix or maintainable byte-bounded prefetch implementation.
Keep prefetch as a conditional research candidate, not another SDK or campaign.
No builds, benchmarks, installations, production edits, CI, owner contact or
foreign code execution were performed in that initial phase. The subsequent
authorized isolated functional prototype is recorded below; adoption remains gated.

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

## Addendum — fixed small-file overlap (source/design follow-up)

**Revised feasibility: conditional go for a small proof, not adoption (medium).**
The proposed fixed cap removes the reservation-framework objection. Three
pending results plus one current result, each at most 64 KiB, bound logical
payload storage to 256 KiB independently of project size or file growth. This
does not bound total RSS to 256 KiB: input buffering, BytesIO/copy transients,
executor objects and exception tracebacks need allowance. No configurable budget,
new API, generic selector or tuning matrix is needed. The earlier implementation
no-go remains the present action; byte accounting alone is **not** a sound reason
to reject this narrower design.

| Concern | Comparison with actual upstream semantics / required boundary |
|---|---|
| Reads, short reads and growth | [tar copy][copy] consumes exactly recorded size in 16 KiB chunks, rejecting a short chunk; it does not demand EOF afterward. A worker must request at most recorded size, never read to EOF or probe one extra byte. Growth is ignored as upstream ignores its tail. A short payload can be passed to unchanged `addfile` via BytesIO so its existing short-read check raises; do not silently shrink TarInfo, pad, or introduce the prototype's length-equality policy. An actual worker read/open exception must retain its type and surface at its member. Coalescing reads is not exact syscall/error timing equivalence, particularly with concurrently modified inputs. |
| Empty/large/nonregular inputs | Upstream opens even zero-size regular files, although tar copies no payload: do not skip that open and suppress its permission/error behavior. Oversized files keep the original open/stream/close path. Links and other nonregular entries keep metadata-only `addfile`. A queue-drain barrier at these entries is a simple conservative alternative to a heterogeneous scheduling framework. |
| Metadata lookahead and errors | Generate/clean TarInfo only on the main thread, in final sorted order; never call shared `tar.gettarinfo` from workers. Filling lookahead can encounter a later `lstat`/cleaning failure before earlier members are written. Store that failure as the next positional queue item, stop filling, finish earlier items, then raise; do not raise immediately from queue filling. Earlier archive/write/read errors must win over later queued errors. This is modest but essential logic. |
| Links and hooks | Serial [gettarinfo][tarstat] preserves its inode bookkeeping order, including metadata-only hardlinks; cached TarInfo must not be regenerated at consumption. Start after PDM has completed selection/update hooks/generated files, and retain finalize and fresh PKG-INFO. No cached selection-era stat or mode manifest. Lookahead still moves stat/open/read earlier in wall time: a path replaced or truncated concurrently can produce a different observation than stock. This is an explicit limitation, not a proof of equivalence for mutable sources; stock also has a stat→open race. |
| Failure artifact / logging | Keep logging after successful serial `addfile`. Prefetch may discover an input error before that member's header is emitted, whereas [addfile][taradd] writes its header before copying. The failed artifact can therefore contain a different partial tail. Exact failed-archive byte identity or identical read chronology is incompatible with ordinary lookahead; successful immutable-input archives and meaningful ordered errors are the credible contract. Do not claim stronger compatibility without maintainer acceptance. |
| Early writer failure / handles | Each task owns its `with open` handle and returns only bounded bytes; the writer never receives live handles. An enclosing `finally` must cancel queued work and call [shutdown(wait=True, cancel_futures=True)][shutdown], including generator early exit. A generator merely abandoned by the caller is insufficient. Preserve the primary writer/ordered-input error; later speculative failures must not replace it. [Cancellation cannot stop running reads][cancel]; joining them may delay failure return on slow/blocked storage. Bounded bytes are not a latency bound. No detached workers or timeout/cancellation framework is justified. |

**Size/maintenance judgment (medium):** A bounded deque, one capped-read helper,
ordered failure item and explicit executor cleanup could plausibly fit within
~80 new/changed production source lines while retaining PDM's existing tar writer.
This is a design estimate, not a counted or reviewed patch. Drain barriers and
lazy executor creation when a first eligible input is encountered keep the scope
understandable, although even tiny projects may pay thread startup. Avoid a
generic scheduler, metadata-policy API or concurrency settings. If ordered
failure/cleanup cannot stay clear within this ceiling, reject rather than hide
complexity in helpers. The remaining lifecycle burden is real but not, by itself,
proof that this restricted patch is disproportionate.

**Maintainer rationale:** PDM alone owns this final serial archive loop; overlapping
only bounded ordinary-file reads could reduce per-file open latency across layouts
without changing selection, hooks, modes, tar/gzip policy or large-file streaming.
The cap makes memory reasoning locally reviewable. That is a credible small
owner-level hypothesis, but speculative reads, failure cleanup and startup overhead
must earn their cost through focused tests and ordinary-command results. Historical
prototype savings still do not establish stock-command value (**low confidence**
in net benefit); P22's stock C screen is separate evidence, not an outcome asserted
here. No implementation or benchmark was run in this follow-up.

**Bounded next proof, only after authorization:** one fixed-cap patch under the
~80-line ceiling and a few extensions to existing tests: exact-cap/over-cap/zero
inputs and ignored appended tail; short read and ordered later metadata/read error;
hardlink plus hook-replaced/generated file; writer failure with queued/running
readers demonstrating closure and join. Use deterministic coordination rather than
a stress framework. Then one standard full-command paired screen, informed by
P22, including tiny and many-small-file layouts and one oversized streaming file;
retain the original report's artifact and contemporary Windows/Mac gates.
Reject on complexity, cleanup failure or immaterial end-to-end benefit.

## Authorized isolated prototype — functional proof only

**Disposition: ready for independent small-diff review, not adoption (medium).**
[pdm-small-read-prefetch.patch](pdm-small-read-prefetch.patch) changes **one official
PDM file**, `src/pdm/backend/sdist.py`: **59 added / 9 removed lines; 68 total**
including imports, helper and replacement loop. No hidden production module,
configuration, API, selector, custom writer or dependency patch exists.
The checkout is ignored at `.upstream`, pinned to the original official commit;
installed PDM and production FastAPI are untouched.

The deque holds at most three pending entries, but the typed loop's `entry`
local can retain the previous completed future/result during the next refill,
despite `del data, future`. Budget conservatively for **four capped payloads
(256 KiB logical bytes at 64 KiB each)**, plus normal buffering, tar/BytesIO
transient copies and executor/exception/thread overhead. The `last` local also
retains an entry reference; in this loop it aliases a queued entry or the
previous/current entry rather than establishing an independent fifth payload.
This corrects the earlier 192 KiB/three-total claim without changing code.
It is not an exact RSS ceiling or a count of physical filesystem read bytes.
Each worker performs one buffered `read(recorded_size)` and owns/closes its input
handle. Growth cannot increase the returned payload above that recorded bound.

Main-thread metadata cleaning and hardlink bookkeeping stay ordered; oversized
and nonregular entries are queue-drain barriers and use the original streaming
or metadata-only paths. Later ordinary metadata/submission/iterator errors are
queued as positional error entries. Ordered `Future.result()` preserves read
failure ordering; earlier writer failures win. An enclosing `finally` cancels
unstarted work and waits for running readers before PKG-INFO/finalization or
exception return. It does not impose a storage-I/O timeout.

### Proof evidence and boundaries

Command, from this owned directory, with `TEMP`/`TMP` pointing at `.proof-work`
on Q: and bytecode disabled: `python -B test_small_prefetch.py`.
[PROOF.txt](PROOF.txt) records **8 passing unittest tests** on existing native
ARM64 Python 3.13.15. This was small functional work, not a benchmark; unittest's
elapsed duration is not a performance result.

* Exact-cap, over-cap and empty inputs: capped worker requests, zero-size opens,
  large-file main-thread chunk streaming and all input closures.
* Appended tail ignored at original recorded length; short payload retains
  stdlib `OSError("unexpected end of data")`.
* Later metadata/read failures appear only after earlier successful member;
  a primary writer error wins over a later speculative read error.
* Actual Q: hardlink **and symlink** remain metadata-only; successful archive
  member payloads/order/types/link targets/modes/ownership/timestamps/PAX fields
  match the unmodified pinned source loaded in memory.
* Real PDM update/finalize hooks replace/remove inputs and create build-dir
  files; dynamic file version and PKG-INFO refresh across two builds. These also
  compare against stock source, not a FastAPI artifact oracle.
* Early writer failure waits for an already-running, handle-owning reader and
  leaves no executor threads alive. A separate deterministically saturated
  one-worker test executor proves the third queued task is cancelled unopened;
  production still requests three workers. Test-only scheduling instrumentation
  is not part of the production patch.

**Gaps:** pytest was unavailable (`ModuleNotFoundError`), so the existing upstream
pytest suite was **not run** and no packages were installed. This proof covers one
flat-package hook layout, not the full upstream src/external-path/platform matrix,
all special files, Python 3.9 compatibility execution or asynchronous interrupts.
There is no full standard-command frontend proof, performance/memory measurement,
Mac run or claim of improved Windows/Mac ratio. Earlier metadata/open timing and
concurrent-mutation observations can differ; failed artifacts may have different
partial tails. Running reads can delay cleanup on slow storage. The requested
bounded normal success/error lifecycle was tested, not arbitrary interruption
or process termination guarantees.

Base-source, patched-source, patch, proof-script and proof-output SHA256 values,
exact revision and line counts are in
[prototype-provenance.json](prototype-provenance.json). Forward applicability was
checked against the pristine checkout index and reverse applicability against
the modified worktree; both were check-only. Checkout, generated archives and
other functional workspace files are ignored, not committed.

**Maintainer rationale:** This is a small PDM-owned overlap experiment around the
existing archive loop, not a novel technique or a FastAPI extension. Its fixed
cap and streaming barriers avoid an allocation scheduler, while standard tar/gzip
and PDM metadata/hooks remain authoritative. The 68-line diff and eight focused
proofs make independent review credible (**medium**); tested immutable-input
semantics and normal error cleanup have **high confidence within these cases**.
Unchanged behavior across the broader upstream matrix and useful full-command
value remain **unproven/low confidence**. Root review should precede any separately
authorized stock-command screen informed by P22; reject if review burden,
compatibility or end-to-end benefit fails the existing maintainer gate.

### Owner-check follow-up — not yet cleared for a standard-command screen

The broad catch now has a **local** `noqa: BLE001`, immediately explaining that
arbitrary failures are queued and reraised in order. It does not globally disable
lint or incorrectly narrow iterator/metadata errors.
The deque is explicitly typed as `Exception | tuple[str, Path, TarInfo,
Future[bytes] | None]`; local narrowing checks an exception **before** tuple
unpacking. No `None`-filled error tuples, casts, new `Any`, classes or framework
remain. The barrier test similarly narrows its last-entry local before indexing.
The full production diff is now **59 added + 9 removed = 68 lines**.

[OWNER-CHECKS.txt](OWNER-CHECKS.txt) retains actual commands and results:
existing **Ruff 0.17.3**, using the checkout's `pyproject.toml`, passes the owner
check, an additional explicit BLE001 check, and format check. This validates the
owner configuration with the available binary, **not** the pre-commit-pinned
Ruff 0.16.6. All eight focused functional proofs also pass again.

**Strict typing remains a check gap, not a pass or asserted source failure.**
Both available interpreters lacked mypy. One isolated installation attempt of
owner-pinned `mypy==2.3.1` into ignored `.upstream/.validation` failed with TLS
`HandshakeFailure` (the installer reported internal retries); no second install
invocation or security bypass was attempted. The actual owner-config mypy
command exits before analysis with `No module named mypy`. Root must obtain a
real owner-config typecheck before authorizing a stock-command screen. Receipt
hashes were refreshed; no performance measurement or CI was run.

**Budget correction / paused:** The conservative four-payload allowance above
accounts for tuple/future aliases introduced by explicit type narrowing.
Production patch, hashes, checks and 68-line footprint are unchanged. Strict
mypy validation still blocks a standard-command screen. Work stops pending
approved owner-pinned tool availability; no further installation attempt or
benchmark is authorized here.

[shutdown]: https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/concurrent/futures/thread.py#L220-L239
[cancel]: https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/concurrent/futures/_base.py#L365-L379
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
