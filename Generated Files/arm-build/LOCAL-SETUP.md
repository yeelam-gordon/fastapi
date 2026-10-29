# Local tools and reproducible network-independent setup

The native interpreter already existed at `C:\Program Files\Python313-arm64\python.exe` (3.13.15, `win-arm64`). The PATH uv executable was broken. This investigation installed an isolated working toolchain without changing the system Python, network configuration or global Git authentication.

| Tool | Installed location | Verification |
|---|---|---|
| CPython | Existing system interpreter; experiment `.venv` | Explicit interpreter-platform check, native execution |
| uv 0.13.6 | `tools\uv.exe` | Official ARM64 archive SHA256 in SOURCES.md |
| pip 26.2.1 | `.venv` | Installed from Python's bundled `ensurepip`, no network |
| PDM backend 2.5.0 | `.venv` | Official source tag resolves to pinned commit; in-tree self-build; installed version checked |
| Ruff 0.17.3 | `tools\ruff.exe` | Official ARM64 archive SHA256 `56cc54ae263ff46a30e095421ff8a93971d9c2dcad2a5e8b64eebc078cac5a16` |
| actionlint 1.7.12 | `tools\actionlint\actionlint.exe` | Official Windows ARM64 archive SHA256 `cadcf7ea4efe3a68728893813643cebe1185e5b1d4be5b96245f65c9a4d5ea41`; workflow validation exit 0 |
| `cProfile` / `pstats` | Python standard library | Direct PDM phase profile executed, artifacts checked against baseline |
| WPR / WPA | Existing Windows installations | `wpr -profiles` succeeds; no shared trace session was started |

The initial local measurements required only PDM and uv because PyPI wheel TLS failed. After the first successful Windows CI job exported a wheelhouse, the complete pinned tool/minimal-runtime set was restored offline into `tools\official-tool-environment`, including native `build`, `psutil`, pytest and Ruff. `pip check` and an installed-FastAPI smoke passed. The original measured `.venv` was retained, so its provenance was not silently changed. The full repository test dependencies/suite were not installed or run.

## Reproduce the successful PDM bootstrap

Use the already verified uv binary, or obtain it through the checksum-checking first part of `provision.ps1`. The complete provisioning script requires registry access or the full CI wheelhouse; the smaller source bootstrap below is the path used for the initial local benchmarks.

```powershell
$root = 'Q:\fastapi\Generated Files\arm-build'
$python = 'C:\Program Files\Python313-arm64\python.exe'
$uv = "$root\tools\uv.exe"
& $uv venv --python $python "$root\.venv"  # Only when the environment does not exist.
& "$root\.venv\Scripts\python.exe" -m ensurepip
git clone --depth 1 --branch 2.5.0 https://github.com/pdm-project/pdm-backend.git "$root\tools\pdm-backend-source"
if ($LASTEXITCODE -ne 0) { throw 'Official source clone failed' }
if ((git -C "$root\tools\pdm-backend-source" rev-parse HEAD) -ne '8c6653726f71afdb2059b44dc9c7706693e95be6') { throw 'Unexpected backend revision' }
& $uv build "$root\tools\pdm-backend-source" --wheel --no-build-isolation --python "$root\.venv\Scripts\python.exe" --no-python-downloads --out-dir "$root\wheelhouse"
if ($LASTEXITCODE -ne 0) { throw 'Backend self-build failed' }
& $uv pip install --python "$root\.venv\Scripts\python.exe" --no-index --find-links "$root\wheelhouse" 'pdm-backend==2.5.0'
if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed' }
```

The source build emits a shallow-clone warning; the expected tag commit and installed version were checked explicitly. The source and built tool wheel stay local and ignored by Git.

## Reproduce the measured build and direct backend profile

```powershell
$root = 'Q:\fastapi\Generated Files\arm-build'
& "$root\.venv\Scripts\python.exe" "$root\benchmark.py" --uv "$root\tools\uv.exe" --repeats 7 --output "$root\results\local-02" --wheelhouse "$root\wheelhouse"
if ($LASTEXITCODE -ne 0) { throw 'Benchmark failed' }
& "$root\.venv\Scripts\python.exe" "$root\profile_backend.py" --source "$root\results\local-02\source" --reference "$root\results\local-02\artifacts\prepare-baseline" --output "$root\results\profile-02"
if ($LASTEXITCODE -ne 0) { throw 'Backend profile failed' }
```

Use a new output directory each time. This builds an immutable snapshot of committed `HEAD`, not uncommitted changes. Raw reports record the exact revision and installed tool versions. Local source-built PDM and CI PyPI PDM must be disclosed if comparing those environments directly.

## Use the candidate for a single local build

After provisioning the dedicated backend environment, the measured candidate is an ordinary complete PDM build without repeated isolation:

```powershell
$root = 'Q:\fastapi\Generated Files\arm-build'
$uv = "$root\tools\uv.exe"
& "$root\.venv\Scripts\python.exe" -c "import importlib.metadata; assert importlib.metadata.version('pdm-backend') == '2.5.0'"
if ($LASTEXITCODE -ne 0) { throw 'Expected dedicated backend version is unavailable' }
& $uv build Q:\fastapi --python "$root\.venv\Scripts\python.exe" --no-build-isolation --no-python-downloads --no-config --out-dir "$root\results\single-build"
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
```

This command builds the current working tree, unlike the immutable benchmark snapshot. It is a local candidate, not an instruction to disable isolation in the existing release workflow.
