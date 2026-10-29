# Revision 2: independent committed-fix verification

**Verdict: HIGH-confidence bounded pass. PC-001 and PC-002 are resolved for the
declared owned canonical-source/PDM 2.5 scope. No remaining consequential
high/medium finding was identified in this follow-up.**

## Revision identity and ownership

- Original blocked candidate: research revision
  `f27aa74bb92af71348f4004f73005cc32b0f26d6`, independently reviewed in
  `REPORT.md` and review commit `0c5a6cfdeeb300c18b866c5f9edfc34eb0218fa0`.
  Its blocked verdict and reproduction receipts remain historical, not claims
  about the fixed candidate.
- **Producer origin fix: `3c10320c9ce03966a4d5f51cd8e8076a1095d235`.**
  Cherry-picked unchanged into this review branch as
  `c13c1ff0b4e2e878b81f5820c7679cc5c7026fb6`.
  `fixed-validation.json` verifies identical candidate content and preserved
  producer author/email/author timestamp. This review does not claim fix
  authorship. No manual producer edits were made.
- Package source remains the separate read-only original
  `79cab5bed28b24d92c185d236feb33f5783dfeb3` checkout; status is clean.
  Builds use owned canonical archive copies, never that checkout.
- Existing official native CPython 3.13.15/PDM 2.5.0 environment; no environment
  provisioning or package changes outside ordinary offline uv build isolation.

## Findings disposition

### PC-001 — Resolved; high confidence

Independent code inspection: `build.py:15-63` checks links/reparse attributes
using `lstat` **before** classifying directories or recognizing backend state.
Only the exact root `.pdm-build` spelling is eligible for exclusion from canonical
input membership. It must be an ordinary directory containing only regular
`.gitignore` and optional regular `pyproject.toml`; its sentinel must read `*\n`.
Unknown files/subdirectories, modified/missing sentinels, noncanonical case
spellings and links/reparse points fail closed. Canonical manifests cannot claim
this namespace (`build.py:77-78`), and disabling PDM cleanup is rejected
(`build.py:69-70`).

This is **narrow structural recognition of disposable backend-owned state**, not
a blanket hidden-directory waiver or an assertion of cryptographic provenance.
Preflight does not parse/reuse stale state metadata. The existing pinned PDM
clean step removes/regenerates recognized state inside the build. No manual
cleanup, extra per-build source copy, or manifest regeneration was used in the
reuse tests. An unrelated unmanifested dot-directory/file still rejects before
output creation and remains intact.

Observed independently on full original-source copies:

1. S1 then S3 on the **same source and same manifest** succeeds.
2. Stock isolated/offline `uv build` B then SDK S3 on its **same source and same
   manifest** succeeds.
3. Further actual SDK CLI S1 then CLI S3 on the reused source both exit 0.
4. Every canonical input hash and the manifest bytes remain unchanged.

### PC-002 — Resolved; high confidence

`selector.py:30-33` rejects root hook names by `casefold()` before PDM builders
are imported/instantiated (`build.py:88-97`). On the actual case-insensitive
Windows Q: filesystem, lowercase, uppercase and mixed-case hook fixtures all
reject before output creation. None writes its harmless execution marker.
Installed-hook and unsupported configuration rejection remain covered.

### Unsafe leftover state — Pass; high confidence within no-concurrent-mutation scope

All six independent state-link gates actually executed, with **zero skips**:
root and nested directory symlinks, root and nested Windows junctions, and
uppercase root aliases for both link types. Every case fails before output
creation, preserves the external owned sentinel's contents and directory
membership, and leaves the link intact for explicit owned cleanup.

The producer's separate junction, unknown-state, modified-sentinel,
canonical-state-claim and disabled-cleanup tests also pass. Sources must not
mutate concurrently with validation/building; these checks do not claim
race-proof hostile-filesystem isolation.

## Independently observed validation

| Validation | Exit/result |
|---|---|
| Original candidate suite (8 tests), producer reuse suite (5), prepared independent fixed gates (11), retained independent non-regression checks (5) | **29 tests, exit 0, zero skips** |
| Same complete selection under Python `-O` | **29 tests, exit 0, zero skips** |
| Fresh workers=3 canonical-source verifier | **0; strict oracle pass** |
| Full-source S1→S3 and stock isolated B→SDK integration | **0; all three SDK strict oracle passes** |
| Actual whole SDK CLI S1 then S3 on reused canonical source | **0 / 0; both strict oracle passes** |
| Read-only Ruff check / format check | **0 / 0** |

All six independently inventoried SDK builds match the unchanged binary Mac
oracle: **1269 sdist members, 65 wheel members**, with complete tar
mode/uid/gid/uname/gname/size, full ZIP Unix modes, payload and metadata hashes,
and RECORD coverage/uniqueness/hash/size/self-row validated. No executable-mode,
payload or RECORD normalization/waiver was introduced. B's exit 0 is not B mode
approval; its previously known Windows five-script mode defect remains explicit.

The independent freshness gate changes actual source payload/version between
SDK calls without deleting backend state or changing the mode manifest; the
second full sdist and wheel contain the fresh payload/metadata. The retained
wheel-provenance check also confirms that changing original inputs after
extraction does not replace the new sdist's wheel inputs.

Evidence: `fixed-tests-normal.log`, `fixed-tests-optimized.log`,
`fixed-golden.json`, `fixed-golden.log`, `fixed-artifact-manifest.json`,
`fixed-integration.json`,
`fixed-integration.log`, `fixed-baseline.log`, `fixed-cli-s1.log`,
`fixed-cli-s3.log`, `fixed-lint.log`, `fixed-format.log`,
`fixed-tools.log`, and `fixed-validation.json`. The latter records origin and
cherry-pick identities, candidate file hashes, source identity/status, exact
validation exits, unchanged-manifest status and strict CLI comparisons.

Reproduction follows `FIX-EXPECTATIONS.md`: use the committed fix, put its
candidate directory on `PYTHONPATH`, run the original suites plus `fixed_checks`
and the five named non-regression selectors under normal/optimized Python, run
the fresh verifier and `fixed_integration_check.py`, and independently inventory
the two additional CLI outputs. All source copies, outputs, uv caches and child
scratch paths used in this follow-up are owned Q: paths.

## Confidence bounds and remaining cost

- **High:** both reported defects resolved; validated backend-state ownership
  boundary; actual hook alias/link/junction rejection; full source reuse and
  strict current-source artifacts on this Windows ARM64 environment.
- **Medium maintenance risk, not an open correctness finding:** exact PDM 2.5
  private API and duplicated discovery remain coupled. Upgrades require fresh
  review and strict verification.
- **Low/unestablished:** Mac-native behavior/performance, any speedup or parity,
  scanner causality and durability across machines. Reading a Mac oracle does
  not establish these.

Safety walking, state validation/cleanup, metadata regeneration and the full
wheel path stay inside each complete SDK CLI invocation. No timing loop,
C: performance experiment, CI, push, source-branch modification, security-setting
change or Mac performance claim was performed. This pass resolves the bounded
code-readiness findings; it is not overall experiment authorization or adoption.
