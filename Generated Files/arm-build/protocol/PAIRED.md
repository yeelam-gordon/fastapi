# Paired ARM experiment v3 — prepared, not authorized or executed

`PROPOSAL.md` and `INTERFACES.md` remain authoritative. This harness does not
change release packaging, endpoint protection, or old evidence schemas.
Integration must provide the sibling `isolated_build.py` and `backend.lock`;
fixture tests do not establish wrapper readiness. No local C: build, hosted
workflow, trace, or performance measurement was executed by this lane.

The manual-only workflow pins its tool checkout to the dispatch SHA and obtains
package source **79cab5bed28b24d92c185d236feb33f5783dfeb3** separately.
Canonical Git archive bytes, Git modes, source manifest, raw helper/lock hashes,
native CPython 3.13.15 executable/shared-library hashes, uv 0.13.6 hash, exact
commands, whitelisted environment changes, logs and artifacts are retained.
Line endings are not normalized by hashing or verification; workflow checkout
disables automatic CRLF conversion. Native macOS universal2 is allowed only when
executing ARM, not Rosetta. Windows runtime, helpers, source, caches, scratch,
dependencies and output live on C:, checked against actual NTFS volume receipts.
Trust/protection status is not inferred or modified.

### Tool checkout scope

Only the research/tool checkout uses non-cone sparse patterns. The pinned
[checkout v7 inputs](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml)
accept newline-separated `sparse-checkout` patterns and
`sparse-checkout-cone-mode: false` for individual files. No `filter` override is
set; checkout v7 requests `blob:none` automatically for sparse checkout. Each job
requires Git >= 2.28 before checkout, rather than permitting the action's
missing/old-Git archive fallback. Anchored patterns retain every immediate
candidate/protocol Python helper,
every lock covered by `code_receipts()`, the setup helper, the receipt-required
`ci_prepare.py`, oracle, workflow and applicable attributes. Historical logs,
result manifests, worktrees and unrelated research are not materialized.

Before copying to the measured volume, each job checks the tracked helper/lock
list against materialized files and explicitly requires the integrated caller
and backend lock. Missing inputs fail; receipt discovery is not silently
shrunk and there is no full-checkout fallback. Adding a new receipt input outside
these patterns requires updating this allowlist. The separate package-source
checkout at 79cab remains complete, with its canonical archive unchanged.
Sparse checkout is a preparation/I/O scope change, not measured performance
evidence. Provision remains separately reported. Attribute policy is integrated
by the root lane; this change does not normalize historical raw evidence.

## Boundaries

One disclosed untimed smoke build per B/S1/S3 precedes the five fixed blocks:
`B,S1,S3; S3,S1,B; S1,B,S3; S3,B,S1; B,S3,S1`.
Each uses a fresh child process/source copy/output. B runs standard `uv build`
with default per-hook isolation; S1/S3 invoke the identical fresh caller wrapper
with workers 1/3. Outer wall includes caller creation, locked offline install,
complete build and wrapper cleanup. SDK isolation is **not** per-hook isolation.
No SDK inner timing substitutes for that outer metric.

Preparation populates hashed, locked offline wheelhouses on both platforms.
Caches are warm; OS page/security caches are uncontrolled. Source copies are
prepared outside the build timer; verification and installed-wheel smoke occur
after exit on **every** smoke/timed sample. Provisioning phases are separate.
Provision plus all build invocations is labeled as this multi-build experiment,
not cold single-build latency. The workflow's provisioning wall starts before
tool/source placement and uv setup, and includes Python acquisition, fixture
gate, archive and wheel preparation. Initial checkouts and post-build
verification costs are not included in that diagnostic sum. Itemized preparation
and Python phases overlap that provision wall and must not be added again.

Each child has 120 seconds; job limit is 20 minutes. Timeout, subprocess failure,
leaked children or unexpected correctness failure stops without replacements and
preserves completed timings. Process-tree CPU is unavailable, never launcher
zero. No trace/scanner attribution is collected.

The independent archive reader checks member counts/names, payloads, complete
tar/ZIP modes, tar ownership/size, metadata and RECORD hash/size/coverage.
The source-specific reviewed Mac oracle remains `candidate/actual-manifest.json`
(1269/65 verified at runtime, not forced into output). RECORD row ordering alone
may differ only after independent self-validation; canonical rows must agree
across every sample. Five exact Windows B script mode losses remain correctness
**FAIL**, with descriptive timings retained; any other failure rejects readiness.
No blanket equivalence flag is emitted.

## Local checks and later analysis

```powershell
python "Generated Files\arm-build\protocol\test_pairs.py"
python "Generated Files\arm-build\protocol\compare_pairs.py" windows-report.json mac-report.json --output comparison.json
```

Comparison fails closed on identity/runtime/schema/schedule/correctness errors,
reports raw walls, medians/ranges, within-block S1−S3 deltas and all variant
ratios, and independently selects min(correct S1,S3) on each OS. B is ineligible
when incorrect or scope-incompatible. Performance goal failure is not an
infrastructure failure. Observed caller-isolated sample parity is neither
durable parity, release adoption nor satisfaction of a per-hook isolation goal.
Adoption scope still needs explicit agreement; preparation is not dispatch
permission.

Unexecuted integration gates: wrapper/selector regression tests, local full
smokes on frozen source, independent artifacts, hosted native runtime/volume
receipts, and the authorized two-job allocation. Cross-day durability and
physical hardware remain separate, explicitly budgeted work.

## Review hardening: PP001 / PP002

Measurement and comparison now enforce the committed caller schema_version 1:
passed status, empty errors, fresh unique owned roots, complete successful
create/install/identity/sdk/cleanup phases, removed environment, native backend
identity, matching commands/workers/source manifest/tool hashes and raw archive
hashes. Phase intervals must be ordered and fit inside wrapper and charged outer
wall clocks. Raw receipts remain retained; malformed receipts cannot establish
SDK parity.

Code identity completeness is checked against the pinned harness commit's Git
tree plus the required versioned inventory, not merely equality of two reports.
Analysis therefore requires that exact commit/tree locally available; there is
no network lookup or missing-inventory fallback. Digests and full revision forms,
native Python/shared-library and uv receipts are required. Runtime binary hashes
are validated independently on each OS, not equated across OSes.

PP003 polling-only process-family ownership remains unresolved pending the
separate lifecycle design decision. These changes do not assert durable
ownership or authorize readiness, C: smokes, benchmarks or CI.
