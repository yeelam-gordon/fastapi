# Toolchain evidence: native does not mean equally optimized

## Observed locally

[native-inventory.json](native-inventory.json) records ARM64 PE machine type `0xaa64` for the tested Python, Node, uv, tar, Git launcher, `_hashlib` and Pydantic core. The inspected interpreter is CPython 3.13.15 built with MSVC 19.44; its zlib build/runtime reports 1.3.1 and OpenSSL reports 3.0.21.

This rules out obvious emulation for those inspected binaries, not for every process/dependency. A native machine type does not establish ARM SIMD use or compiler optimization quality. Windows sysconfig reports several build flags as unavailable; missing values mean unknown, not disabled.

## Primary-source finding: optimization levels must be distinguished

At tag `v3.13.15`, CPython's Windows project properties enable `MaxSpeed`, intrinsic functions, whole-program optimization and release link-time code generation. Its release wrapper explicitly says x86 and ARM64 releases do not use profile-guided optimization (PGO), while the x64 path passes a PGO job.

Sources: [PCbuild project properties](https://github.com/python/cpython/blob/v3.13.15/PCbuild/pyproject.props), [release wrapper](https://github.com/python/cpython/blob/v3.13.15/Tools/msi/buildrelease.bat), [build arguments](https://github.com/python/cpython/blob/v3.13.15/PCbuild/build.bat).

Therefore “Windows Python is unoptimized” is too broad. **Release optimization and PGO are different questions.** The source default is relevant evidence, not proof of the exact flags used for every installed official or standalone binary. A corresponding Mac build-recipe/provenance check is still needed before attributing a performance gap to compiler flags.

The follow-up [standalone provenance audit](PROVENANCE.md) independently checked published ARM64 artifacts: Windows standalone 3.13.15 **does use PGO**, and Mac uses PGO+LTO. Do not apply the stock MSI-wrapper omission to the managed CI distribution. A custom PGO rebuild is not justified by the current evidence.

The PCbuild README contains older platform descriptions; the actual build scripts recognize ARM64. Do not infer platform support from stale prose alone.

## Measurement gate before a custom interpreter build

First establish the target workload and identify how much wall time is CPU work in Python, native codec work, source compilation, dependency installation or file/scanner waits. Compare representative operations and actual library/build provenance. A codec optimization cannot explain or remove unrelated process, metadata or filesystem costs.

Do not compile a custom Python or change CPU/security settings merely because PGO is absent from a wrapper default. Such an experiment needs a measured CPU-bound target, a supported native toolchain, compatible artifacts and enough expected benefit to justify build/maintenance cost. The prior ensurepip POC is audited separately and must not be conflated with a compiler optimization.
