# Portable bounded-prefetch candidate — not adopted for release

Python 3.13 and **pdm-backend==2.5.0** must already be provisioned. No new
toolchain, payload cache, global monkeypatch, custom TAR writer or Node runtime.

```
python build.py --source SOURCE_COPY --source-manifest MANIFEST.json --out-dir NEW_OUTPUT --workers 3
python -m unittest -v test_candidate
python verify.py --source-repo READ_ONLY_GIT_CHECKOUT --reference MAC_ARTIFACT_DIRECTORY
ruff check .
ruff format --check .
```

`--workers 1` is the serial control; `3` uses the standard-library
ThreadPoolExecutor with three pending reads. The writer consumes in PDM order;
its current payload plus three futures bounds live buffers by count, not bytes.
Both preserve normal extraction attributes. Source and output must be separate;
output must not exist. Source must be an owned, clean canonical Git archive copy,
not the shared source checkout. `verify.py` creates that copy under ignored
`scratch/`, using command-scoped `core.autocrlf=false` (no Git settings changed).
For another verification, remove only this candidate's ignored scratch first.

Manifest format: relative POSIX names mapped to `{"mode": 420}` or `493`
(0644/0755); legacy non-executable 0664/executable 0775 also accepted. All source
paths must be present. Optional SHA fields are evidence, not a payload cache:
each invocation reads current source bytes and regenerates PDM metadata,
sdist selection, and archive-derived wheel selection. Concurrent source mutation
is unsupported; size changes during an individual read fail explicitly.

## Evidence and limits

`verification.json` records a full build from source revision
`79cab5bed28b24d92c185d236feb33f5783dfeb3` and strict comparison against the real
Mac artifacts from CI 40814588064. `actual-manifest.json` retains payload hashes,
full TAR permissions/ownership/size and full ZIP Unix modes. All 1269 sdist
members and 65 wheel members match; wheel RECORD coverage, hashes and sizes
are independently checked, including the metadata files themselves. As in the
foundation oracle, timestamp/compression bytes are not normative.
`functional.log` retains build output. First export attempt correctly failed
strict comparison because Git's host newline conversion was active; corrected
canonical export passed without weakening the oracle.

No new performance benchmark, Mac execution, cross-OS parity or frozen-number
claim is made. Foundation `filesystem/stdlib-ops` measured C: serial 3.303s
versus threaded-with-attributes 2.426s. Optional no-attribute extraction saved
only another 0.037s and is deliberately omitted. Evaluate this same optimization
on **both** operating systems before any adoption.

## Maintenance / attribution

Adapted from foundation bfc3067's stdlib-ops experiment and archive selector.
Uses the standard ThreadPool mechanism, not a novel concurrency algorithm.
The source-reviewed prior crutkas pip parallel **bytecode** work is a separate
implementation, not this implementation or its measured workload.

Private coupling is limited to SdistBuilder.build_artifact,
`_package_metadata`, `_show_add_file`, clean_tarinfo and PDM naming utilities;
WheelBuilder remains unchanged. The exact version guard runs before builder
imports. A PDM upgrade requires source review, discovery/metadata guard updates,
and strict artifact revalidation. Only file-based version and the observed
top-level-package/source-includes configuration are supported. Hooks, backend
paths, src discovery, source globs, unusual modes, links, traversal and
unsupported PDM options fail closed with ValueError. Narrow duplication of PDM
discovery and the extra source safety scan are explicit maintenance/runtime
costs. There are no Windows-only runtime paths, executable assumptions or
architecture guards (including no rejection of native Mac universal2).

## Revision 2: independent review follow-up

Both PC-001 and PC-002 were independently reproduced before fixing:
`rev2-repro-repeat.log` records unchanged-manifest reuse rejection;
`rev2-repro-hook.log` records the mixed-case hook reaching the writer instead
of being rejected before loading. Original evidence above remains historical.

Preflight now distinguishes only the exact root `.pdm-build` directory with
PDM 2.5's `*\n` sentinel and optional regular `pyproject.toml` from canonical
inputs. These recognized files remain untouched by preflight: PDM's existing
clean step removes/regenerates its own state **inside every build call**.
There is no per-build source copy or external cleanup. Unknown state, modified
sentinels, canonical claims on this directory, noncanonical case aliases,
links/reparse points (including Windows junctions), and disabled PDM cleanup
are rejected before output creation. Source trees must not mutate concurrently
with safety checks/building; these checks do not claim race-proof isolation.
Local hook names are rejected case-insensitively on every platform.

`verify_reuse.py` prepares one source per family, then exercises S1→S3 and
ordinary isolated/offline `uv build`→S3 with unchanged canonical manifests.
`rev2-verification.json` and `rev2-*.log` retain new evidence. All three SDK
builds match the unchanged Mac full-mode/RECORD oracle (1269/65 members).
Stock build success is not stock artifact approval: its historical Windows
mode discrepancy remains outside this fix. No performance or Mac-native
execution claim is added.
