# Checkout/input readiness: committed-fix rerun

## Final bounded gate — inventory fix works on the reviewed integration

Producer commit `d5536b5931378c81f2be6cb36090aa3259047494` was
attributed-cherry-picked as `d3e454b08874a5552c387621070e1460983df2be`.
Only committed inputs were examined; no producer working files were read.

- **Exact producer SHA fails completeness, correctly:** its committed tree lacks
  `protocol/backend.lock`, `protocol/isolated_build.py`, and
  `protocol/test_isolated_build.py`. The SHA-scoped negative receipt explicitly
  records these missing required inputs, not an omitted or mismatched hash.
  This producer-only tree is not the integrated wrapper tree.
- **Integrated SHA passes the static/input gate:** production
  `tool_inventory()` and `code_receipts()` now agree with independent full-tree
  enumeration and all 22 actual file hashes in both Windows Git EOL
  configurations. All LF-declared inputs remain canonical; workflow
  `core.autocrlf=false` still protects un-attributed YAML and archive export.
  Complete separate source remains 3,233 files at the pinned 79cab revision.
- **31 focused tests pass:** 14 harness (including the new real-Git regression),
  6 wrapper, 11 lifecycle. This deep review scratch initially exceeded Windows
  Git's path limit in the regression fixture. That raw failure is retained.
  The final `longpaths` attempt uses **process-only** `core.longpaths=true`
  for test subprocesses; no machine or global configuration was changed.
- The two tested SHAs deliberately differ. The exact producer SHA includes its
  helper lineage; this integrated review branch retains the earlier 6aba helper
  cleanup lineage. Each receipt pins its actual input revision and hashes.
  No cross-revision helper equivalence or mismatch is claimed.

Receipts: `receipts/reruns/<SHA>/`; final passing integrated evidence is under
`receipts/reruns/d3e454b08874a5552c387621070e1460983df2be/longpaths/`.
The original blocker and its receipts below remain historical, unmodified.
An optional `--attempt <simple-name>` preserves separate attempts beneath a SHA.

**Confidence/limits:** high for the exact local static/input assertions above;
medium for hosted-action correspondence; Mac runtime, actual CI C: placement,
and full build/readiness remain unverified. These are Windows Git EOL tests,
not Mac execution. Pending wrapper-B/harness-argv CW002 changes are outside
this gate. No CI, performance run, or full-readiness claim.

## Original gate — preserved blocker history

Reviewed integration `38ff65b812b29f2c6362295229c03726b9b65657`.
No producer changes, CI dispatch, builds, traces, global Git configuration, or
other-worktree writes. Original root tracked status remained clean.

## High-confidence blocker

`protocol/measure_pairs.py:88-95` runs
`git -C <tools>/Generated Files/arm-build ls-tree -r --name-only <revision>`.
Git reports subtree-relative names there (`candidate/build.py`, etc.), but
`REQUIRED_TOOL_INPUTS` contains repository-relative names. Consequently actual
`tool_inventory(revision)` raises **Committed tool inventory is incomplete**
in both fresh sparse checkouts. `code_receipts()` and preparation cannot finish.
Use repository-root enumeration or `ls-tree --full-tree` in the producer lane,
then rerun integration. Fixture tests currently miss this real-Git boundary.
This proof does not patch or monkeypatch production discovery.

## Verified independently

- Both actual workflow sparse blocks are identical. Fresh local shared clones,
  no full research checkout, materialize exactly **22 required hash inputs**
  plus three applicable attribute controls. No historical evidence, research
  documents, environments, worktrees, or private/user-note paths materialize.
  Only tracked public inputs were inspected; ignored private data was not read.
- Independent full-tree enumeration applies the production inventory predicate
  and required set. Missing `owned_process.py` raises, rather than shrinking
  the inventory. Wrapper, backend/setup/tool locks and oracle are present.
- Command-scoped `core.autocrlf=false` and `true` checkouts retain identical
  Git-canonical raw hashes for every LF-declared helper, lock and oracle.
  Un-attributed workflow YAML and `.gitattributes` become CRLF with `true`;
  raw attribute hashes and `check-attr` output are retained. Attribute parsing
  still enforces LF. No hash normalizes captured bytes.
- This is **Windows EOL configuration testing, not macOS execution**.
  The actual workflow already sets command-environment `core.autocrlf=false`,
  protecting the YAML and canonical archive. YAML EOL sensitivity is not a
  deployed-workflow defect. The proof explicitly mirrors that environment for
  production archive preparation, rather than inheriting local Git settings.
- Separate complete source checkout at
  `79cab5bed28b24d92c185d236feb33f5783dfeb3` and production canonical archive:
  **3,233 regular files**, every payload SHA256 matches its Git blob, every
  manifest mode matches Git `100644`/`100755`, no Generated Files inputs,
  source clean before/after, no `.pdm-build`. Git modes, not Windows filesystem
  executable-bit emulation, are authoritative. Source and harness identities
  remain separate in `receipts/proof.json`.
- Focused protocol tests: **13 harness + 6 wrapper + 11 lifecycle tests pass**.
  Raw stdout/stderr are committed unchanged under `receipts/`.

## Reproduction and remaining gate

From this worktree root, run
`python -B "Generated Files\arm-build\reviews\checkout-inputs\prove.py" --revision <full-committed-integration-SHA>`.
The original receipts above remain immutable. Subsequent runs write only to
`receipts/reruns/<SHA>/`, refusing to overwrite an existing run. The optional
revision defaults to this review branch's HEAD. Committed Git objects, never
uncommitted producer files, supply the checkout. Once production discovery
succeeds, its inventory and `code_receipts()` must match the independent
enumeration and actual byte hashes; no positive result can rely solely on
the independent fallback.
The script requires its owned `.scratch` directory not to exist; remove only
that directory before repeating. Clones reference local Git objects and never
copy unrelated tracked research into their working directories.
Receipts pin the tested revision; integrating these review files changes the
harness revision, not the tested helper content.

**Confidence:** high for local sparse completeness, LF bytes, source identity,
and the inventory blocker; medium for correspondence to hosted checkout action
behavior (patterns exercised by Git, action not executed); low/unverified for
native macOS/ARM, CI C: NTFS placement and runner runtime. Fix real-Git discovery,
rerun readiness, then obtain explicit authorization for the remaining integrated
smoke/hosted gates. No performance, Mac parity, PGO mapping or protection claim.
