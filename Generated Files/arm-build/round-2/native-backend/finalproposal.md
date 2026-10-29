# Round 2: native uv_build fast-path proof

## Decision

**Not a drop-in optimization; target not achieved.** The installed native uv 0.13.6
successfully builds the complete FastAPI sdist and a wheel **from that sdist** using
its bundled backend. However, the unchanged dynamic-version declaration fails.
A disposable, AST-resolved static-version probe builds in **1.660 s median**
(five standard, nonverbose trials), still above the **0.730 s** comparison target.
All five artifacts fail the existing strict equivalence check. No validator,
production source, canonical source, current benchmark or dependency manifest
outside this owned directory was modified. No CI or subagents were used.

## Evidence and measurement boundary

Read `..\..\FINDINGS.md` first: its Mac number is an observed runner result, not an
accepted strictly identical cross-platform benchmark; five executable-mode
differences remain in the prior Windows/Mac comparison.

This proof used native Windows ARM64 CPython **3.13.15**, installed official
PDM backend **2.5.0** for the reference context, and native
`uv 0.13.6 (329bf9448 ... aarch64-pc-windows-msvc)`. The reference is
`results\local-03-canonical\artifacts\repeat-01-candidate`, built from canonical
source revision `264cbad400c8336057a70b9b6a65bfdb4920321e`.

| Standard trial | AST resolution + config generation + full build, seconds |
|---|---:|
| 1 | 1.660445 |
| 2 | 1.597905 |
| 3 | 1.669708 |
| 4 | 1.621783 |
| 5 | 1.774274 |
| Median | **1.660445** |

`probe.py` reads and AST-parses `fastapi\__init__.py` on **every timed trial**,
extracts literal `__version__ = "0.162.0"` without importing FastAPI, writes the
disposable configuration, and waits for the full `uv build` subprocess. Timing
includes version resolution, metadata/config generation, frontend startup, sdist
selection/compression, extraction, wheel metadata and wheel writing. No retained
metadata or prebuilt archive is substituted. Offline mode and distinct initially
absent output/cache directories prevent a cached artifact win. Source/filesystem
caches are warm; this is not cold-machine provisioning.

Copying the immutable source into the disposable tree and post-build validation
are excluded, as in the retained canonical build-only harness. Installed Python
and uv bootstrap are excluded; the bundled backend needs no new installation or
download. No Python dependencies were installed.

The earlier five **verbose diagnostic** trials are separately retained in
`rawreports\report.json` (median 1.741422 s); do not mix these with the five
standard trials in `rawreports\standard\report.json`. The diagnostic trace
explicitly says `Using bundled uv_build backend` and
`Building wheel from source distribution...`. Debug overhead is not included in
the headline.

## Supported configuration and hard blockers

Official documentation recommends a compatible bounded requirement, currently
`uv_build>=0.13.6,<0.14`. This proof pins `uv_build==0.13.6` to the installed uv,
with `build-backend = "uv_build"`. The bundled path avoids provisioning a backend
wheel. A frontend other than uv instead needs the separate `uv_build` package.

The default layout is `src\<normalized-project-name>\__init__.py`; FastAPI needs:

```toml
[tool.uv.build-backend]
module-root = ""
module-name = "fastapi"
source-include = ["tests/**", "docs_src/**", "scripts/**", "docs/en/docs/img/favicon.png"]
```

Recursive anchored includes matter: uv's singular `source-include` is not PDM's
`source-includes`. The package, README and declared license are included by
default; bytecode/cache directories are excluded. This configuration preserves
all canonical required source files, including tests, documentation examples,
scripts, favicon and package data.

**uv_build 0.13.6 does not support nonempty dynamic metadata.** Its tagged
`metadata.rs` rejects nonempty `project.dynamic`; `project.version` is required.
Our otherwise unchanged dynamic-version probe exits **2**, reporting missing
field `version`, before the later explicit dynamic-metadata validation.
`rawreports\standard\dynamic-failure.stderr.log` preserves the failure.
PDM's version-from-file setting is not implemented by uv_build. Replacing
`dynamic = ["version"]` with a static version is an **incompatible source metadata
change**, not an accepted optimization, even though its resolved version agrees.

The tagged direct-build guard requires `build-backend = "uv_build"` and exactly
one `uv_build` build requirement. It checks compatibility against the running
version/known compatible versions, and active exact pins must match the binary.
A custom dynamic-metadata wrapper is therefore not a transparent way to retain
the existing bundled fast path.

## Exact compatibility differences

Every standard build was checked with the **unchanged imported**
`benchmark.py` archive validator, including complete wheel RECORD hash/size
validation and sdist executable bits. Detailed member hashes, exact textual
diffs and metadata values are in each trial of
`rawreports\standard\report.json`.

| Artifact | Canonical PDM | uv_build | Exact differences |
|---|---:|---:|---|
| Wheel regular members | 65 | 65 | Same names; three differing members below |
| Sdist regular members | 1,269 | 1,270 | Extra `pyproject.toml.orig`; two differing common members below |

Wheel changes:

1. `fastapi-0.162.0.dist-info\METADATA`: uv additionally emits
   `Author: Sebastián Ramírez`; `Author-email` is unchanged. The four
   `Provides-Extra` fields and 44 `Requires-Dist` fields are reordered;
   requirement formatting also changes. Parsed requirements (name, extras,
   specifier, marker, URL) and the set of extras are equal. README metadata body
   is identical. Exact strings are retained in `rawreports\metadata-semantics.json`.
2. `...\WHEEL`: `Generator: pdm-backend (2.5.0)` becomes `Generator: uv 0.13.6`.
3. `...\entry_points.txt`: uv omits PDM's empty `[gui_scripts]` section.
   The console entry point remains `fastapi = fastapi.cli:main`.

`RECORD` bytes necessarily differ to describe the changed files; the unchanged
validator verifies every entry before normalizing this generated listing.

Sdist changes:

1. `PKG-INFO`: the same metadata differences described above.
2. `pyproject.toml`: our explicit backend/static-version/layout changes, **plus**
   uv's documented TOML 1.0 reserialization, including formatting/comment changes.
3. Extra `pyproject.toml.orig`: the disposable changed input configuration, **not**
   the unmodified canonical PDM configuration.

No canonical member is missing. All other common member bytes and sdist
executable bits match the retained **Windows canonical PDM reference**. Licenses,
`py.typed`, package/version source, tests, `docs_src`, scripts and favicon are
preserved. This does not resolve the older Mac executable-mode discrepancy.
A zip-import smoke of the produced wheel returned version `0.162.0`, imported
from the wheel rather than the checkout, and found the CLI main callable.
It is a smoke, not an installed-wheel or full test-suite claim.

Integrity comparison covered all **3,392 copied canonical files**: only the
disposable `pyproject.toml` differs. See `rawreports\final-verification.json`;
that receipt describes the initial diagnostic proof. The final standard builds
use the same disposable config/content and independently validate each archive.
`rawreports\standard\final-verification.json` additionally records the standard
wheel smoke, current probe fingerprint, and identical differences on all five
standard builds.

## Smallest principled next route

Do **not** adopt this backend switch under strict identity. Even adding uv dynamic
version support would leave the rewritten pyproject/original member, Generator,
metadata serialization and entry-point differences. No supported setting found
disables all these behaviors.

Instead, prototype an archive-writer substitution **below PDM's existing metadata
and file-selection logic**, not another project backend:

1. Keep the original dynamic pyproject and PDM file selector/version resolver.
   Generate fresh PDM metadata and entry-point bytes each build; never reuse this
   experiment's retained metadata as the production input.
2. Hand PDM's ordered member manifest, exact generated bytes and permission policy
   to an audited native tar/gzip and zip/RECORD writer. Preserve PDM-visible
   metadata and source bytes, not uv_build's metadata/pyproject rewriting.
3. Actually extract the resulting sdist, then resolve metadata/select wheel files
   from that extracted input and write the wheel. Include every phase and any
   helper startup/provisioning in the measured boundary.
4. Require the current validator to pass on **every trial** before discussing
   latency. Settle the five Mac executable bits explicitly rather than ignoring
   them. A separate raw-byte-identical archive requirement, if intended, also
   needs timestamp/order/compression-header checks beyond this retained validator.

The next concrete experiment is a bounded PDM metadata/selection versus
archive-writing timing split using the installed PDM, followed only if warranted
by a small native archive-writer proof. uv's public build CLI does not expose
"write these supplied PDM metadata bytes" as an optimization switch.
No native writer was implemented here; no unmeasured speedup is promised.

## Confidence and primary sources

**High:** native bundled path exists; dynamic-version drop-in fails; exact listed
artifact differences; all required canonical contents preserved; five standard
builds completed and rejected strict identity.

**Medium:** native archive work can reduce a material serial Python/file-processing
component, consistent with current FINDINGS profiling. The observed 1.660 s is
specific to this local VM and incompatible probe, not a comparable cross-platform
speedup. It remains about **2.27×** the 0.730 s target.

**Low:** a compatible hybrid will reach 0.730 s or beat a physical Mac. No such
measurement exists; even this incompatible native probe needs about **56%**
further reduction.

Public primary sources are listed in `rawreports\primary-sources.json`.
Tagged Rust sources are retained with hashes and snapshots. Both documentation
pages were successfully read through the web-fetch tool; the separate attempt to
download their HTML with Python received HTTP 403, also preserved in the receipt.

- https://docs.astral.sh/uv/concepts/build-backend/
  — bundled backend, supported layout, includes and rewritten pyproject/original.
- https://docs.astral.sh/uv/reference/settings/#build-backend
  — module-root/name, source-include/exclude and defaults.
- https://github.com/astral-sh/uv/blob/0.13.6/crates/uv-build-backend/src/metadata.rs
  — exact version guard and dynamic-metadata rejection.
- https://github.com/astral-sh/uv/blob/0.13.6/crates/uv-build-backend/src/source_dist.rs
  — unconditional pyproject rewriting/original addition and source traversal.
- https://github.com/astral-sh/uv/blob/0.13.6/crates/uv-build-backend/src/wheel.rs
  — native wheel construction and metadata/Generator handling.

## Scoped housekeeping

The local `.gitignore` excludes `snapshots\source\`, `cache\`, `cache-standard\`,
`scratch\`, `.venv\`, `tool-environment\`, `__pycache__`, and binary
`*.whl`, `*.tar.gz`, `*.tar`, `*.zip`, `*.exe`, `*.dll` files under this experiment
only. Source copies and binary outputs remain locally available as evidence
without publishing duplicate FastAPI trees. Scripts, JSON manifests/reports,
text traces/diffs, source receipts and this proposal remain visible.
