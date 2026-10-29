# Independent prefetch code/failure-path review

**Disposition: readiness blocked by PC-001.** Fresh canonical-source artifact
checks pass; this is not approval for the shared-source paired experiment.
Reviewed `candidate/build.py`, `ops.py`, `selector.py`, `validate.py`,
`test_candidate.py`, and `verify.py` at research revision
`f27aa74bb92af71348f4004f73005cc32b0f26d6`, against official PDM 2.5.0 source.
No producer files, source branches, CI, protection settings, or Mac artifacts
were modified. All retained scratch/source copies are under this owned Q: lane.

## Consequential findings

### PC-001 — High readiness impact; high confidence

**Location:** `candidate/build.py:33-42` (whole-source scan/manifest equality);
interaction with PDM `Builder.build()` and `SdistBuilder.get_files()`.

**Observed:** a successful SDK invocation leaves
`.pdm-build/.gitignore` and `.pdm-build/pyproject.toml` in its source copy. A
second invocation on that same prepared source with the original canonical
manifest fails before creating output:
`ValueError: Source files must exactly match canonical manifest paths`.
Stock isolated `uv build` also leaves those two files, then SDK fails identically.

**Expected:** the protocol's single prepared source must support B/S1/S3 and
subsequent blocks without incorporating generated state or invalidating the
unchanged canonical input manifest. Rejecting truly unexpected source files
remains necessary; adding generated files to the authoritative manifest is not
a fix.

**Reproduction:** `integration_check.py` exports two fresh copies of the original
79cab canonical archive, runs S1 then S3 on one, and stock isolated/offline uv B
then S3 on the other. Both first builds succeed; both second SDK calls fail.
`integration.json` retains exact commands, unchanged-manifest receipts and
generated-file names. `repeat-cli.log` confirms the actual SDK CLI exits **1**.
The minimal independent tests reproduce both sequences as well. Assertions
expecting the defect pass; that does **not** make the implementation correct.

**Consequence:** every predeclared ordering eventually fails if one prepared
source is reused; the isolated golden smoke cannot establish paired readiness.
Producer must explicitly resolve source/build-state ownership and retest reuse.
Do not silently remove arbitrary inputs, regenerate the manifest, waive the
safety scan, or move necessary per-invocation cleanup outside the charged timer.

### PC-002 — Medium; high confidence on case-insensitive filesystems

**Location:** `candidate/selector.py:30-33`; preflight call in `build.py:38`.

**Observed:** hook rejection tests exact string membership for `pdm_build.py`.
A source containing `PDM_BUILD.PY` passes this guard on Windows Q:, but PDM's
`BuildConfig.custom_hook` checks the filesystem for the lowercase name and finds
and executes that same file. Our harmless hook writes `hook-ran.txt` into its
owned output. Only afterward does the writer fail with
`Missing canonical mode: pdm_build.py`, since manifest spelling is uppercase.

**Expected:** unsupported local hooks are rejected before PDM loads/executes
them, regardless of filesystem case aliases.

**Reproduction:** run
`python -B -m unittest -v review_checks.ReviewChecks.test_reproduce_case_variant_hook_execution`
from this directory with candidate on `PYTHONPATH`. The test confirms preflight
acceptance, the later mode error, and the executed-hook marker. Both normal and
optimized Python reproduce it.

**Bounds:** no such hook exists in frozen 79cab; this does not demonstrate
corruption of its golden artifacts. The result directly contradicts the declared
fail-closed hook boundary. Case-insensitive Mac volumes plausibly share the
aliasing concern, but were not executed here. This is a configuration-contract
finding, not a broader vulnerability assessment.

## Other reviewed guarantees and explicit limits

- **Current-source correctness:** fresh workers=3 full build passes the local
  immutable Mac oracle; a separate fresh workers=1 full build passes too.
  Inventories are 1269 regular sdist members / 65 wheel members, with 64 selected
  source files. Comparison retains full tar mode/ownership/size and wheel Unix
  modes, payload/metadata hashes, and independently verifies RECORD membership,
  uniqueness, hash, size and self-row. No executable-bit normalization or waiver
  was introduced. B's known five-script Windows mode defect remains a failure;
  B's integration exit 0 here is **not** baseline artifact approval.
- **Selection/configuration:** manually traced PDM package/stub discovery,
  source-includes exclusions, rewritten pyproject, file-version metadata and
  license inputs. Existing/independent tests reject traversal, archive links and
  duplicates, unsupported options/backend paths/source globs, SCM/call version
  sources, local lowercase hooks and installed plugin hooks. The intended narrow
  scope does not promise a generic frontend. PC-002 is an actual gap, not a
  demand to support rejected configurations.
- **Freshness/provenance:** independent builds change actual payload and version
  metadata without changing the mode manifest; the freshness check explicitly
  removes owned `.pdm-build` between calls because PC-001 otherwise stops it.
  A controlled post-extraction mutation of the original source does not change
  the wheel: payload and metadata come from the newly built sdist. Optional
  manifest SHA fields are documented evidence, not enforced hashes; immutable
  canonical-byte identity remains a caller/preparation responsibility.
- **Errors and resources:** normal and optimized tests cover missing source
  reads, target-write errors, generator close/cancellation/thread joins, the
  three initial read bound, invalid/extra/missing manifest paths and modes,
  existing/nested output rejection and the exact backend-version gate. Exceptions
  are not swallowed; the CLI propagates nonzero. Read/write failures may retain
  partial output and PDM build state; the CLI does not promise transactional
  rollback. Read-only ACL denial and arbitrary concurrent source mutation were
  not independently tested.
- **Thread/memory bound:** three futures at most, ordered consumption; executor
  context joins running work, including writer-failure unwinding. The current
  yielded payload plus pending futures is a count bound, not a bytes limit.
  A hung filesystem read has no inner timeout; outer timeout remains necessary.
- **Timing:** the new recursive safety/stat walk and manifest comparison run
  inside `build()` before PDM. Whole CLI/wrapper timing therefore includes them,
  imports, metadata, source reads, compression, selection, normal-attribute
  extraction and wheel construction. No benchmark was run; old prototype inner
  timings do not establish this candidate's complete-command performance.
- **Portability/coupling/names:** no Windows runtime path or architecture check
  appears in candidate code; stdlib data-filter extraction and ordinary
  attributes are retained. Windows reads of the Mac binary oracle are not Mac
  execution or performance evidence. Exact PDM 2.5.0 guard precedes builder
  imports; private writer/metadata/logging/naming and duplicated discovery remain
  maintenance risks requiring re-review on upgrades. Important role names are
  reasonably clear; the README explicitly explains that manifest hashes are
  optional and that workers=1/3 are serial/prefetch controls.

## Reproducible validation

Use the existing official environment (native CPython 3.13.15 ARM64,
pdm-backend 2.5.0); do not install dependencies:

```powershell
Set-Location 'Q:\fastapi\Generated Files\worktrees\prefetch-code-review\Generated Files\arm-build\reviews\prefetch-code'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Resolve-Path '..\..\candidate').Path
$python='Q:\fastapi\Generated Files\arm-build\tools\official-tool-environment\Scripts\python.exe'
```

For fresh reproduction of integration/golden evidence, ensure this lane's
`scratch` does not already exist, then:

```powershell
New-Item -ItemType Directory -Force 'scratch\candidate' | Out-Null
Copy-Item '..\..\candidate\*.py' 'scratch\candidate'
& $python -B 'scratch\candidate\verify.py' --source-repo 'Q:\fastapi\Generated Files\worktrees\source-fastapi' --reference 'Q:\fastapi\Generated Files\arm-build\results\ci-40814588064\macos\ci\artifacts\prepare-baseline'
& $python -B integration_check.py
& $python -B -m unittest -v test_candidate review_checks
& $python -B -O -m unittest -v test_candidate review_checks
& 'Q:\fastapi\Generated Files\arm-build\tools\ruff.exe' check '..\..\candidate' review_checks.py integration_check.py
& 'Q:\fastapi\Generated Files\arm-build\tools\ruff.exe' format --check '..\..\candidate' review_checks.py integration_check.py
```

Observed final exits: **0 / 0 / 0 / 0 / 0 / 0**. Both test modes run 17
tests, including tests expecting the two reproduced defects. Stock uv uses
ordinary isolated full sdist-then-wheel builds, offline wheels, owned Q: cache
and child scratch. No timing comparison, CI dispatch, push, dependency install
outside build isolation, or source-branch modification was performed.

Execution disclosure: an initial minimal-fixture uv probe used uv's default
cache/scratch locations before explicit Q: settings were added. It was not a
benchmark. All retained final uv reproductions, including both full-source
integration paths, explicitly route child scratch and cache to owned Q: paths.
