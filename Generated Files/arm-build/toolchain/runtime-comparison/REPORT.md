# C: native Python distribution comparison

## Result

**No persuasive distribution advantage in these small warm isolated-package-build samples.**
This is a runtime-choice experiment, not an optimization of FastAPI, not a pure
PGO experiment and not a Windows/macOS performance comparison.

Wall seconds; three alternating pairs per command; backend environment creation,
backend installation, full sdist creation and wheel-from-sdist are inside timing:

| Default-isolation frontend | Stock 3.13.15 samples | Managed 3.13.15 samples | Stock median [range] | Managed median [range] |
|---|---|---|---|---|
| `uv build` | 5.855, 6.099, 5.787 | 6.002, 6.442, 5.884 | 5.855 [5.787–6.099] | 6.002 [5.884–6.442] |
| `python -m build --installer pip` | 13.367, 13.201, 13.566 | 13.184, 12.754, 13.159 | 13.367 [13.201–13.566] | 13.159 [12.754–13.184] |

Managed/stock median ratios: **1.025** for uv and **0.984** for build/pip.
Opposite small effects, three samples, overlapping ranges and no process-tree CPU
measurement do not support a reliable runtime recommendation or compiler attribution.
Both sample sequences use stock/managed, managed/stock, stock/managed ordering.

## Controls and preparation

- Host: existing Windows ARM64 Cobalt 100 VM, not the physical-machine target.
  C: is the protected NTFS lane; no security settings were changed.
- No Python download, installation, compilation, CI dispatch or concurrent
  benchmark inside this lane. Existing stock and uv-managed interpreters were
  found and verified before fresh venv creation.
- Owned scratch: `C:\fastapi-arm-build-lab\runtime-ab-2a73e36a\attempt-2`.
  Binaries, venvs, source, backend environments, caches, temporary directories,
  logs and artifact outputs used during measurement reside on C:.
  Shared source worktree was only read by Git; it was never changed.
- Immutable source revision: `79cab5bed28b24d92c185d236feb33f5783dfeb3`,
  original FastAPI 0.162.0 with no research trees. Preparation creates one
  canonical LF tar, normalizing CRLF only in UTF-8, NUL-free members.
  Both runtimes then use exactly the same extracted source, without between-run
  copying. The 2,859 normalized member names and both tar hashes are retained.
- Copied uv 0.13.6 and the master `ci-40814042898` wheelhouse onto C:.
  Wheel hashes were checked against its receipt; both fresh venvs were restored
  offline using the same full hash-locked `tooling.lock`, including build 1.6.1,
  pip 26.2.2 and PDM backend 2.5.0. No prior patched pip/ensurepip was installed.
- Separate initially empty cache per runtime/frontend; one excluded warm-up
  per cell. All samples use offline find-links and PDM constraints, fresh output
  directories, same source and same cache policy. Bytecode writing is **not**
  disabled. There is no `--no-build-isolation` or direct backend substitution.
- Preparation outside timing: **16.554 s**, including source archive,
  wheelhouse/reference copying, inventory and tooling restore. Fresh stock
  venv/hash-sync: 0.065/1.407 s; managed: 0.058/0.722 s.
  Excluded warm-ups: uv stock 17.235 s, uv managed 6.238 s;
  build/pip stock 14.672 s, managed 14.967 s. These asymmetric warm-ups are not
  evidence of a steady-state runtime gain.
- Full successful harness run: **189.137 s**. An initial preparation attempt
  stopped at its explicit LF assertion before any build: Git archive exported
  CRLF. That root was retained, not deleted. The successful attempt explicitly
  canonicalized the archive before extraction/timing.
- No SDK-prefetch third cell: kept this bounded unit to the requested real
  standard frontend controls, without importing another worker's evolving code.

Exact argv/environment and unrounded samples: [evidence/results.json](evidence/results.json).
`measure.py` is the formatted reusable harness. `executed-measure.py` freezes the
exact executed source, whose SHA256 is
`4fa7c8e55c46b213378a84e7128f3224eef6d5b22715c8e1ec7244a333dbc6d6`.
The observed-bytecode diagnostic also has an exact frozen executed copy.

## Runtime identity and limits

Both base executables and `python313.dll` are native ARM64 PE machine `0xaa64`,
with file/product versions 3.13.15. Both report MSC v.1944.

| Distribution/file | SHA256 |
|---|---|
| Stock python.exe | `7944f73d1dc202232cd0f615d14f909603af1cd00d6a3ff98dac51c49259c44b` |
| Stock python313.dll | `0d7ca3451d6a5bd62ce8c45498290581cbbbfb2c073b3a507bdca9d9874c1d81` |
| Managed python.exe | `383d0ff495b7a4903426037fa003f72963aaebd4f1aa3cd08a22895421c703bd` |
| Managed python313.dll | `1eca9e2e85bb5ea49ad6452b2603272ff8245357bf98a41bdb96f35c1479511f` |
| uv.exe | `ec27977d62b5f6091bce410a8e69d40d07541803314e0120905c0ad0affaa5cc` |
| Canonical LF source tar | `3d47d694782ff61e8fd74536d2fef3b50e8f4508715c66650187f7ca542f70d3` |

Stock: `C:\Program Files\Python313-arm64\python.exe`, build tag
`tags/v3.13.15:4061bc4`, Aug 5 2026.
Managed: existing `uv python find --managed-python 3.13.15`, under
`<USERPROFILE>\AppData\Roaming\uv\python\cpython-3.13.15-windows-aarch64-none`,
build date Sep 29 2026. Personal path prefixes in exported evidence are redacted;
only that redaction is applied to raw logs, not measurement/artifact data.

Stock versus managed codec/runtime inventory:

| Component | Stock | Managed |
|---|---|---|
| zlib compile/runtime | 1.3.1 / 1.3.1 | 1.3.2 / 1.3.2 |
| OpenSSL | 3.0.21 | 3.5.9 |
| SQLite | 3.50.4 | 3.53.1 |
| bz2/lzma | installed DLL extension modules | installed DLL extension modules |

Module paths are recorded; no unsupported bz2/lzma library-version or SIMD
dispatch inference is made. [Published provenance](../PROVENANCE.md) verifies
standalone Windows PGO release metadata, not an exact download receipt for this
pre-existing executable. The official MSI wrapper's default non-PGO configuration
does not prove the optimization flags of this exact stock binary.
The A/B also changes standard library, linked codecs, build and layout.
It cannot isolate PGO, compiler quality, antivirus or any one cause.

## Installer and actual bytecode path

Captured installed `build.env._PipBackend` source and runtime property checks show,
for both venvs, valid outer pip, no virtualenv, and `venv.EnvBuilder(with_pip=False)`.
Dependency installation uses outer pip with `--python <isolated-python>` and
`--no-compile`. Thus ensurepip and prior pip byte-compilation fixes are off this
measured call path. The default complete sdist-to-wheel flow creates two isolated
backend environments; logs explicitly report installed PDM 2.5.0.

Persistent PDM pycs in the tooling/cache trees were zero before/after every build;
that does **not** mean transient imports produced none. Separate untimed,
intrusive filesystem observations found a peak **34 actual PDM `.pyc` files in
each of the four runtime/frontend cells** while their backend environments lived.
Those diagnostic durations are not samples. See `transient-pycs.json` for paths
and observation counts. No forced dontwritebytecode was used.

CPU is explicitly null: neither uv's parent CPU nor a Windows venv launcher's
zero would measure the descendant workload. Wall results cannot distinguish CPU,
file waits, caching, endpoint scanning or process setup.

## Artifact acceptance and validation

Same-OS reference for every build is the existing canonical Windows standard
`python -m build` preparation at
`C:\fastapi-arm-build-lab\frontends-2a73e36a\outputs\prepare-A`, copied once onto C:.
Reference hashes and manifests are retained; there is no per-runtime baseline.
Every whole wheel/sdist pair passed member-name/content equality, wheel RECORD
hash/size checks and **full** ZIP external mode/TAR mode equality to that reference.
Twenty pairs were rechecked: 4 warm-ups, 12 samples, 4 untimed pyc diagnostics.
Per-member hashes/modes for benchmark builds and whole-artifact SHA256 for all
20 pairs are retained, including diagnostics in `verification.json`.

The Mac CI reference remains a **strict failure**, not a waiver: the same five
sdist shell scripts have identical content but missing Windows execute bits
(`format.sh`, `lint.sh`, `test-cov-html.sh`, `test-cov.sh`, `test.sh`).
All sixteen benchmark/warm-up comparisons explicitly retain these five diagnostics.
No Mac timing or cross-platform parity claim follows from this experiment.

Checks: full executed experiment, `verify.py` all-artifact recheck, native uv PE,
executed-harness fingerprint, and Ruff lint/format checks on maintained scripts.
Frozen executed copies intentionally preserve pre-format source.
Confidence is high for these local identities/artifact checks and low for a
general performance ranking from three warm pairs. No result establishes the
original Windows-at-least-as-fast-as-Mac goal.
