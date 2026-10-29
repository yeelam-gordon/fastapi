# Standalone ARM64 interpreter provenance

## What was independently checked

The source audit downloaded the following full release archives into memory, calculated their SHA256 digests, matched those to GitHub release metadata and inspected embedded `python/PYTHON.json`. No interpreter from those downloads was executed or installed.

Release `20260929` resolves to standalone commit `b498734a5791d0e6786695a226fd398a41c6f7f6`.

| Published full archive | Embedded optimization metadata | SHA256 |
|---|---|---|
| `cpython-3.13.15+20260929-aarch64-pc-windows-msvc-pgo-full.tar.zst` | Windows ARM64; Python 3.13.15; `optimizations=pgo`, `build_options=pgo` | `14c46f0e1f15e4c45004a52b492de849b8ca947333661426ceb0b55c0041cbcf` |
| `cpython-3.13.15+20260929-aarch64-apple-darwin-pgo+lto-full.tar.zst` | Mac ARM64; Python 3.13.15; `optimizations=pgo+lto`, `build_options=pgo+lto` | `f6d0b397d62a6041ef67ca5180fe989fc0acbd3058ffc31c8ab4b43cae1ba430` |

Primary artifact source: [release 20260929](https://github.com/astral-sh/python-build-standalone/releases/tag/20260929). The receipt identifies archive members/fields, not invented source line numbers.

## Windows is not generically “unoptimized”

The standalone Windows ARM64 recipe performs PGInstrument, runs the instrumented target interpreter against training tests, then builds PGUpdate. Source defaults for CPython also enable whole-program optimization and release LTCG. Therefore the metadata label `pgo`, rather than Mac's `pgo+lto`, does **not** prove Windows lacks link-time optimization.

Sources: [ARM64 target, lines 425–444](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/ci-targets.yaml#L425-L444), [PGO build/training, lines 1630–1712](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/cpython-windows/build.py#L1630-L1712), [CPython flags](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/PCbuild/pyproject.props#L54-L107).

The inspected Mac artifact records `-O3 -arch arm64`, `--enable-optimizations --with-lto=full`, profile-use flags and matching native build/host triples. That supports the Mac PGO+LTO description; it does not quantify a compiler advantage.

Sources: [Unix optimization configuration](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/cpython-unix/build-cpython.sh#L500-L503), [PGO/LTO options](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/cpython-unix/build-cpython.sh#L568-L577).

## Installed binaries and codec limits

Release code maps ordinary ARM64 install-only distributions to Windows `pgo` and Mac `pgo+lto`. The managed CI interpreters are consistent with that release family, but the existing CI reports lack executable hashes/download receipts. This is a supported mapping, not byte-for-byte proof of each executed CI binary. The earlier MSI-based interpreter is a separate provenance category.

Source: [release variant mapping](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/src/release.rs#L84-L93), [Mac mapping](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/src/release.rs#L143-L149).

The Windows standalone builder selects ordinary zlib for 3.13 and zlib-ng from 3.14. Native execution and codec versions do not establish active SIMD/CRC dispatch. Representative codec CPU measurements are needed before attributing elapsed time to missing ARM acceleration.

Source: [Windows codec selection](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/cpython-windows/build.py#L1467-L1474).

## Decision

Do not rebuild Python on the assumption that the managed Windows distribution lacks PGO—it does not. A supported stock-versus-managed distribution comparison can be useful on one Windows machine, but it changes more than one compiler flag and must not be called a pure PGO experiment.

First measure the real slow stage, current-process and child CPU versus wall time, actual dependency/source-build activity, codec share and file waits. A custom interpreter build needs stronger expected value than a missing sysconfig field.

Confidence: high on published artifact metadata/recipes; medium on mapping existing CI runs to those artifacts; causal performance impact remains unestablished.
