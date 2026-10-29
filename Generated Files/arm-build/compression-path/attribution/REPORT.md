# P20: one official public-sdist codec attribution

**Decision:** deflate is material enough for narrowly gated, shared-toolchain
research; CRC alone is negligible here. No rebuild or adoption is justified.
This is a diagnostic, not a frontend benchmark, SDK timing, speedup estimate,
compiler proof, or Windows/Mac parity result.

## Executed once

Evidence: `codec-attribution-9a73f3ea23c7\`. All preparation commands succeeded;
their complete output and return codes are retained. The one profiled operation
imports `pdm.backend` in a fresh process and calls its public
`build_sdist(out)` once, with official **pdm-backend 2.5.0**. There is no private
hook/writer/selector, codec policy change, wheel build, network, CI, or SDK run.

The original FastAPI source is commit
`79cab5bed28b24d92c185d236feb33f5783dfeb3`, archived with
`git -c core.autocrlf=false archive` from the existing read-only
`Q:\fastapi\Generated Files\worktrees\source-fastapi` snapshot (the original
FastAPI79 tree; this installation's directory is named `source-fastapi`).
Archive commit and every extracted source file's bytes were checked before use.
No shared source was built or modified.

The unique owned NTFS root is
`C:\fastapi-arm-build-lab\codec-attribution-9a73f3ea23c7`.
Runtime, fresh environment, backend, wheelhouse, helper, source, cache, temp,
output and raw profile all reside there. Managed Python was found using
`uv python find 3.13.15` and copied read-only from its managed installation;
the shared installation and shared environments were not mutated.
uv **0.13.6** and the locked official wheel were copied to C:.
Offline installation uses the explicit owned hash-pinned `backend.lock`;
Python 3.13 needs no additional backend dependencies. `summarize.py` also checks
every installed backend `.py` against the official wheel, without another build.

Native **CPython 3.13.15**, MSC v.1944 ARM64, has built-in zlib
**1.3.2**, compile/runtime versions equal. All inherited Python environment
variables were removed; `PYTHONDONTWRITEBYTECODE` and `PYTHONPYCACHEPREFIX`
are absent, and the child confirms `dont_write_bytecode=False`,
`pycache_prefix=None`. Default bytecode policy was used, not P22's rejected
suppression policy. Existing copied runtime bytecode can be warm; no cold-cache
claim is made. Protections/trust/elevation were unchanged.

## Actual attribution

Overall attributed call region: **2.0887574 s wall**, **1.796875 s process CPU**.
cProfile's default timer measures elapsed/performance time, **not CPU time**.
Its setup/import, helper imports and object construction are outside this region;
backend import and public build are inside. Process startup, environment
preparation, profile serialization, stats processing and verification are outside.
The helper's top-level standard-library imports include `tarfile`, which
preloads `gzip` and `zlib`; their module-import cost is therefore outside.
`pdm.backend` itself is first imported inside the fresh child region. This is
not a cold import-cost measurement of every transitive standard-library module.
Wall timing includes the enable/disable boundary; total profiler self-time is
2.0882915 s. These boundaries explain the small difference.

| Native leaf | Calls | Self elapsed seconds | Region wall share |
|---|---:|---:|---:|
| `zlib.Compress.compress` | 231 | 0.2463150 | 11.7924% |
| `zlib.Compress.flush` | 1 | 0.0002390 | 0.0114% |
| `zlib.crc32` | 232 | 0.0030105 | 0.1441% |
| `zlib.compressobj` | 1 | 0.0000434 | 0.0021% |
| All four disjoint native zlib leaves | 465 | 0.2496079 | 11.9500% |

Compress + flush is **0.246554 s / 11.8039%**. No native `decompress` or
`adler32` calls occurred in the profiled region; these are absent, not filtered
out. `stats.json` retains **all 1,482 entries and caller relationships**;
`stats.txt` is also untruncated. `profile.json` includes all codec-name matches,
including non-codec buffer flush/class entries; `summary.json` explicitly
separates the native zlib leaves. No top-40 filtering was used.

Inclusive wrappers are deliberately separate: TAR `addfile` is 0.5604604 s
(1,269 calls); gzip's two `write` implementations are 0.2651756 s (3,542 calls)
and 0.2529732 s (231 calls); public `build_sdist` is 2.0807719 s inclusive.
**Do not add these nested cumulative times**, or add them to the leaf total.
Profiled native time may include scheduling/blocking and profiler perturbation;
the fractions are diagnostic observations, not unprofiled CPU fractions.

## Package verification and retained identity

The independent standard-library TAR reader counts the produced inventory:
**1,269 regular files**, no duplicate members. This count was observed, not
required by the reader. Existing independent Mac standard-build oracle:
`results\ci-40814588064\macos\ci\artifacts\prepare-baseline`.
The existing `candidate\validate.py` comparison function checks full member
names, payload SHA256, sizes, uid/gid, uname/gname and modes; its fixed-count
combined sdist/wheel reader was intentionally not called. No wheel was needed.

All payload and compared metadata agree except the known five script modes:
`format.sh`, `lint.sh`, `test-cov-html.sh`, `test-cov.sh`, `test.sh` under
`fastapi-0.162.0/scripts/` are **0644 Windows versus 0755 oracle**.
**Strict oracle comparison FAILS**, as stock Windows does; nothing was fixed or
waived into a strict success. The complete package and expected-only mode
differences are recorded in `verification.json` and `inventory.json`.
Timestamp/gzip-byte identity is not asserted by this semantic oracle.

`preparation.json` records exact source/tool/runtime/wheel/helper hashes and all
commands; `profile.json` records backend origin/version/hash and Python DLL
hash. The built-in codec's binary container is `python313.dll`, SHA256
`1eca9e2e85bb5ea49ad6452b2603272ff8245357bf98a41bdb96f35c1479511f`.
Raw `build.prof` SHA256:
`6221c83a381f43053431c3cb5f62018dcc5d2314585e99e05d4c1f24bf6fcf73`.
The raw profile is retained both at the C: root and ignored beside the text
receipts; binaries/source/environment remain outside tracked evidence.
`summary.json` retains the runtime gzip source hash and actual source lines
showing raw deflate (`-zlib.MAX_WBITS`) and separate CRC calls.

## Confidence, unknowns, and maintainer gate

* **High:** this execution's unchanged official backend, source bytes, complete
  archive payload, known mode failure, and observed native leaf times/call counts.
* **Medium:** deflate is worth a later bounded shared-toolchain evidence gate;
  one instrumented run establishes attribution, not typical cost or gain.
* **Low:** actual ARM instruction paths, compiler/PGO/LTO causes, deployed Mac
  codec identity, and any contribution to a matched Windows/Mac performance gap.

The source recipe distinction in the parent report remains source evidence,
not proof that this DLL lacks CRC instructions or a particular deflate path.
CRC's ~3 ms does not explain the ~246 ms raw-deflate leaf. No new binary-code
inspection or causal compiler experiment was performed. Historical old profiles
have different environments/boundaries and are **not directly comparable**.

Prefer the common Python/codec distribution/toolchain owner, not a FastAPI
patch. Before any later implementation experiment, require actual binary/build
path evidence and a supported, maintained distribution option relevant to
**deflate**, not a CRC-only conjecture. Any adoption proposal would additionally
need meaningful unprofiled full-command gain, repeated supported-tool evidence,
complete artifact checks, best-correct Mac comparison, and explicit owner,
compatibility, review-size and upkeep justification. Portable best practices
rank second; bespoke SDK/private-backend integration and custom runtime/codec
rebuilds remain no-go. This evidence bundle is not a FastAPI build dependency.

## Reproduction boundaries

`attribute.py` is the one-shot offline coordinator; it copies its executed
profile helper to C:. Running it again creates a new diagnostic, so **do not**
rerun merely to inspect these results. `summarize.py <evidence-directory>`
only verifies retained bytes and derives the native summary; it does not
profile/build. The recorded execution used the managed interpreter with `-I`
for the coordinator and normal default bytecode policy for the C: child.
