# Checkout/input readiness: blocked on production inventory discovery

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
