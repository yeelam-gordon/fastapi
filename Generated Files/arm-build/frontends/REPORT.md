# Standard isolated frontends, current FastAPI, C:

## Result

Completed three alternating trials per frontend, after one **untimed verbose preparation per frontend**.
All nine timed commands succeeded and passed canonical same-Windows artifact validation.
These are existing upstream tool features, not an original packaging optimization.

| Frontend | Wall samples (seconds) | Median |
|---|---|---:|
| A: `python -m build` (default pip installer, isolation) | 13.894, 13.421, 13.206 | **13.421 s** |
| B: `python -m build --installer uv` (isolation retained) | 9.590, 9.862, 9.672 | **9.672 s** |
| C: `uv build` (default isolation) | 5.961, 6.081, 5.906 | **5.961 s** |

B reduces this sample's median by 27.9% relative to A; C by 55.6% (2.25x).
These are full-command differences, **not** separately measured environment-creation costs.
Order: ABC, CBA, ABC. Dedicated caches were warmed, not cleared between trials.
Fresh outputs and fresh backend isolation are included in every timed command.

Authoritative completed evidence: [evidence-c87512b2b70d/results.json](evidence-c87512b2b70d/results.json).
Raw stdout/stderr, help, installed source snapshots, per-build manifests and full permission modes
are adjacent. [measure.py](measure.py) orchestrates standard tools; it does not package anything.

## Workload and commands

- FastAPI **0.162.0**, canonical Git archive commit `264cbad400c8336057a70b9b6a65bfdb4920321e`.
  Archive PAX commit verified; canonical LF bytes retained.
- Native CPython **3.13.15**, MSVC 19.44, `win-arm64`.
- `build==1.6.1`, `pip==26.2.2`, **pdm-backend==2.5.0** (not the PDM application),
  `packaging==26.3`, `pyproject-hooks==1.3.3`.
- uv **0.13.6**, commit `329bf9448`, reported `aarch64-pc-windows-msvc`.
  Copied binary SHA-256: `ec27977d62b5f6091bce410a8e69d40d07541803314e0120905c0ad0affaa5cc`.
- Fresh owned workspace:
  `C:\fastapi-arm-build-lab\frontends-2a73e36a\c87512b2b70d`.
  Existing workspaces were never overwritten.

Below, `$R` denotes that workspace; the executable and all source/environment/wheelhouse/cache/
temporary/output paths actually used are on C:. The orchestrator and evidence sink are on Q:.
Exact expanded argument arrays are in `results.json`.

```powershell
& "$R\env\Scripts\python.exe" -m build "$R\source" --outdir "$R\outputs\<fresh-A>"
& "$R\env\Scripts\python.exe" -m build "$R\source" --outdir "$R\outputs\<fresh-B>" --installer uv
& "$R\tools\uv.exe" build "$R\source" --python "$R\env\Scripts\python.exe" --out-dir "$R\outputs\<fresh-C>" --build-constraints "$R\backend-constraints.txt" --no-create-gitignore
```

Default commands build an sdist, then extract it and build the wheel from that sdist.
No `--no-isolation`, `--no-build-isolation`, direct wheel-only build, backend override,
custom packager, or source packaging patch was used.
`--no-create-gitignore` suppresses only uv's extra output marker.
Installed `--help` was checked before builds. Local snapshots of the dependency's
implementation are retained for analysis but ignored by Git; public source
references and version pins identify the upstream implementation.

## Setup, timing and offline policy

The final workspace preparation before build commands took **12.913 s**:
copy canonical archive once and extract, copy/verify offline wheelhouse against its SHA-256 inventory,
copy/verify uv, create native venv, and `uv pip sync --require-hashes` using the copied existing
`tooling.lock`. Hash-locked sync took **1.412 s**, venv provisioning **0.272 s**.
The existing lock also installs its psutil/ruff pins; neither participates in packaging.
All checkout/copy/tool provisioning and artifact verification are outside command timers.
Complete successful run, including those steps and validation, took **140.864 s**.

Untimed verbose preparations: A **21.981 s**, B **9.829 s**, C **6.140 s**.
Timed commands omit `-v` and preserve unfiltered raw stdout/stderr.
Timing starts before spawning the frontend and ends after process exit: backend environment
creation, install, hooks, sdist/wheel work and frontend cleanup are included.
No reliable per-phase timings were collected; verbose diagnostics are call-path evidence only.

Process-only environment settings are recorded in full:
`PIP_CONFIG_FILE=NUL`, `PIP_NO_INDEX=1`, `PIP_FIND_LINKS=<C-wheelhouse>`,
`PIP_CONSTRAINT=<C-constraint>`; `UV_FIND_LINKS`, `UV_CONSTRAINT`,
`UV_BUILD_CONSTRAINT`, `UV_CACHE_DIR`, `UV_OFFLINE=1`, `UV_NO_CONFIG=1`,
`UV_PYTHON_DOWNLOADS=never`, `UV_NO_MANAGED_PYTHON=1`, and C: `TEMP`/`TMP`.
The constraints file pins `pdm-backend==2.5.0`.
`UV_NO_INDEX=1` was also set, but installed uv help does **not** advertise that environment
variable. Therefore no claim is made that uv honored it: **UV_OFFLINE=1 is the effective
network prohibition**. uv verbose output includes an attempted registry lookup message;
offline resolution nevertheless selects the local wheel. No online resolution is required.
No global configuration, AV settings, UAC, trust settings or CI were changed.

No forced `PYTHONDONTWRITEBYTECODE` or `sys.dont_write_bytecode` is used for frontend/backend
processes. Normal bootstrap/import bytecode policy applies. A's installed upstream build code
itself passes `--no-compile` to pip; this is not our patch.

## Observed isolation call paths

The installed `build/env.py` and `build/__main__.py` are copied alongside the logs.
Runtime probe: outer pip valid **True**, virtualenv available **False**,
`_create_with_virtualenv=False`, ensurepip used by build **False**.

- **A:** `DefaultIsolatedEnv` -> `_PipBackend` -> standard-library
  `venv.EnvBuilder(symlinks=False, with_pip=False)` on Windows. The valid outer
  pip is hosted in the tool environment and runs `python -m pip --python <fresh-env-python>
  install --ignore-installed --use-pep517 --no-warn-script-location --no-compile --no-input -r ...`.
  Two fresh isolated environments and two PDM installations are visible in the diagnostic log.
  **No virtualenv or ensurepip branch executes here.**
- **B:** `_UvBackend` still calls stdlib `venv.EnvBuilder(..., with_pip=False)`;
  it discovers the copied external uv through PATH and runs `uv pip install pdm-backend
  --python <fresh-env-python>`. Two fresh isolated environments, each installing 2.5.0.
  This switches the dependency installer, not all environment creation to `uv venv`.
- **C:** uv log explicitly rejects its `uv_build` direct-build path because the configured
  backend is `pdm.backend`. It installs 2.5.0 in two distinct fresh
  `cache\uv\builds-v0\.tmp...` environments, calls sdist hooks, then wheel-from-sdist hooks.
  Cached wheel data is reused; backend environments are freshly created.
  uv internals below the emitted diagnostics were not instrumented.

Windows GetProcessTimes values in JSON cover **only the launched process**, not its children.
For A/B the Windows venv launcher consumes near-zero CPU while actual work runs in descendants.
Those values are not valid end-to-end CPU comparisons; **aggregate workload CPU is unavailable**.

## Artifact proof and reference limits

The canonical same-OS reference is this run's untimed **A** output, independently built with
default `python -m build`. B/C preparations and every timed A/B/C output match its complete
sdist/wheel filenames, member sets, file-content hashes and **full tar/zip permission modes**.
Every wheel RECORD row is checked for hash, size and membership coverage before comparing the
verified listing; archive timestamps/compression and RECORD row ordering are not parity claims.

The older Windows CI reference is **not** a canonical-byte baseline: its source members contain
CRLF, whereas this Git archive and the macOS reference contain LF. An initial strict comparison
failed rather than silently normalizing this difference. That historical reference is retained
in `windows-reference.json`; the new reference is `canonical-windows-reference.json`.

Separately, every final output differs from the macOS reference in exactly **five sdist
executable-bit entries**, with identical corresponding file bytes:
`scripts/format.sh`, `lint.sh`, `test-cov-html.sh`, `test-cov.sh`, and `test.sh`.
Windows has no execute bits; macOS has `0111`. These differences remain failures of
cross-OS permission parity: **no waiver, normalization or cross-OS parity claim**.
Wheel member content matches that macOS reference after RECORD validation.

Two preliminary attempts are retained, not mixed into timing samples:
`evidence-frontends-2a73e36a` stopped at the historical CRLF mismatch;
`evidence-1d20191ee22e` stopped because uv's default output `.gitignore` violated the strict
two-artifact check. The final fresh workspace used the advertised marker-suppression flag.
No failed output directory was recycled.

## Confidence and scope

- **High:** actual full isolated command costs for these nine observations; pinned backend;
  canonical same-OS member/content/RECORD/mode equivalence; observed build call paths.
- **Medium:** relative warmed-cache ordering for this current native workload, based on only
  three alternating trials on a shared machine, without statistical or cold-machine controls.
- **Low / unsupported:** attributing all differences to pip alone, CPU savings, broad workload
  forecasts, any reproduction of **FastAPI 0.119.1 / Python 3.12.10**, or the unverified
    user-supplied metric. This experiment establishes none of those.

Bounded experiment complete; no additional matrix or security changes.
