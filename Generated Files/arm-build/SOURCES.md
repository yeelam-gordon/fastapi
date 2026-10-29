# Verified research sources

Read on 2026-10-28/29. Documentation is evidence for tool behavior, not measured speed. Runner images and version catalogs can change; raw execution metadata takes precedence.

| Primary source | Verified fact and consequence |
|---|---|
| [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) | Public `windows-11-arm` is ARM64 with 4 CPUs and 16 GB RAM. `macos-15` is ARM64 with 3 M1 CPUs and 7 GB RAM. These are not equal-resource or physical 20-versus-16-core machines. `windows-latest` is x64; explicit ARM labels and runtime assertions are needed. Standard hosted public-repository runners are free. |
| [setup-python advanced usage](https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md) | Exact Python patch pins avoid drift but may cost provisioning time if absent from the tool cache. Record provisioning separately rather than hiding it inside package timing. |
| [Python runner versions manifest](https://github.com/actions/python-versions/blob/main/versions-manifest.json) | Queried manifest includes 3.13.15 ARM64 artifacts for both `win32` and `darwin`. This checks availability before choosing the CI matrix; successful setup still needs execution evidence. |
| [uv distribution builds](https://docs.astral.sh/uv/concepts/projects/build/) | uv is the build frontend; PDM determines archive contents. Default `uv build` builds an sdist then a wheel from that sdist. `--wheel` alone is not an equivalent workload. Build constraints pin isolated backend versions. With isolation disabled, installed dependencies are not reverified by uv, so bootstrap remains hash-checked and isolated release checks remain important. |
| [uv cache semantics](https://docs.astral.sh/uv/concepts/cache/) | Registry cache behavior follows HTTP metadata. A dedicated cache and offline measured trials separate network transfer from package work. Same-filesystem caches avoid cross-filesystem copy fallback. Do not equate `--no-cache` with an entire cold machine or modify cache internals directly. |
| [CPython 3.13 profiling](https://docs.python.org/3.13/library/profile.html) | `cProfile` and `pstats` explain function cost but add overhead; profiles are diagnostics, not the benchmark samples. Subprocess attribution needs separate handling. |
| [Official uv 0.13.6 release](https://github.com/astral-sh/uv/releases/tag/0.13.6) | Installed `uv-aarch64-pc-windows-msvc.zip`; SHA256 `c2426c0c8e28b53d8c440e47a18d96ad4db51e159866c0e81435b196d7f0081c` matches GitHub release asset digest. Native executable reports `aarch64-pc-windows-msvc`. |
| [PDM backend 2.5.0 build configuration](https://github.com/pdm-project/pdm-backend/blob/8c6653726f71afdb2059b44dc9c7706693e95be6/pyproject.toml) | `requires = []`, in-tree backend `pdm.backend.intree`, `backend-path = ["src"]`; Python 3.13 has no required external runtime dependencies. This enables the successful official-source self-bootstrap without changing TLS protection. |
| [Official Ruff 0.17.3 release](https://github.com/astral-sh/ruff/releases/tag/0.17.3) | Downloaded the native ARM64 Windows archive and matched its SHA256 release-asset digest before running lint/format checks. |

## Engineering hypotheses, not sourced performance promises

The expert method in [PROFILING.md](PROFILING.md) operationalizes these tool facts: define an unchanged artifact, time each phase, alternate repeated comparable trials, retain raw failures, inspect the critical path and accept only artifact-equivalent results. Pinning tools does not make different CPUs equivalent. More cores accelerate parallel work only; FastAPI's current pure-Python packaging has no compiler-job setting to scale across all cores.
