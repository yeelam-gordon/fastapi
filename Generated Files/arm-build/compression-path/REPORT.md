# P20: ARM compression-path investigation

**Decision:** one later bounded attribution diagnostic is justified. A custom
zlib/Python rebuild, compiler switch or compression-policy change is not.
Compression contributes measured work, but its contribution to the matched
Windows/Mac gap remains unknown. This proposal does not change or block the
current frozen candidate.

The research agent returned its findings inline without creating files; this
report preserves that delivery. The local metadata probe below was reported by
the agent; its original stdout was not separately retained. No build,
microbenchmark, installation, foreign patch execution or CI run was performed.

## Evidence and proposal table

| Hypothesis | Evidence | Unknown / discriminating next check | Confidence |
|---|---|---|---|
| Compression is packaging work worth attributing | Historical sdist profile: `zlib.Compress.compress` 0.221 s / 1.659 s, about 13.3%; wheel: 0.011 s / 0.159 s, about 6.9% | These omit flush and are diagnostic profiles, not matched benchmark shares. Retain all codec entries in a later unchanged-workload profile | High for historical observations |
| Windows ARM may miss an available CRC instruction path | Managed recipe pins classic zlib 1.3.2; its ARM CRC guard requires `__aarch64__`, `__ARM_FEATURE_CRC32` and eight-byte words, with GNU-style inline assembly | Actual managed binary code generation was not inspected; obtain build/preprocessor evidence or bounded disassembly | Medium source inference; low causal attribution |
| Mac codec implementation can differ despite equal Python versions | Standalone Mac recipe omits a built zlib dependency and normalizes linkage to `/usr/lib/libz.1.dylib`; published Apple sources contain ARM64 vector CRC assembly | Exact CI library, deployed Apple revision and active path remain unknown; collect module linkage/version metadata later | High recipe distinction; low deployed-binary attribution |
| CRC acceleration explains the profiled deflate time | Not established: Python gzip uses raw deflate and updates CRC separately | Attribute deflate, flush, CRC and output writes separately, with identical real inputs/settings | High rejection of conflation |
| A codec/toolchain replacement is justified now | No Windows-specific end-to-end benefit has been demonstrated | Require a supported distribution, meaningful full-command gain, full artifact verification and best-correct Mac comparison | High no-go |

Historical compression time alone is not evidence that compression explains
the entire performance gap. Current SDK profiling reports `gzip.write`
inclusive time 1.024 s and `_write_raw` inclusive time 0.321 s within 3.129 s
wall / 3.016 s process CPU. These nested inclusive times must not be added or
called codec-only CPU. The earlier profiling environment caveat remains.

## Local metadata observation

The agent resolved native managed Python using the verified uv executable's
`python find 3.13.15`, then invoked that interpreter with `-B` for metadata only:

| Field | Reported value |
|---|---|
| Python | 3.13.15, Sep 29 2026 build |
| Compiler / machine | MSC v.1944 64 bit (ARM64) / ARM64 |
| zlib module origin | built-in |
| `ZLIB_VERSION` / `ZLIB_RUNTIME_VERSION` | 1.3.2 / 1.3.2 |
| `CC`, `CFLAGS`, `CONFIG_ARGS`, `PY_CFLAGS`, `PY_CFLAGS_NODIST`, `LDFLAGS`, `PGO_PROF_USE_FLAG` | null |

Missing sysconfig fields do not establish absent optimization. This observation
does not identify the earlier CI executable byte-for-byte. Stock CPython's
Windows default zlib 1.3.1 and the managed recipe's 1.3.2 override are distinct.
The existing verified Windows PGO versus Mac PGO+LTO labels do not establish
absent Windows LTCG or active CRC/SIMD paths.

## Later acceptance gate and upkeep

After the current experiment, retain complete `compress`, `flush`,
`decompress` and `crc32` profile entries for the unchanged packaging workload.
Record exact runtime identity, codec versions and linkage before any supported
distribution comparison. A stock/managed comparison changes multiple variables
and cannot isolate compiler or PGO effects.

Any faster compatible implementation may also benefit Mac. Preserve current
compression levels, gzip/ZIP formats, payloads, executable modes, metadata and
RECORD checks; changed compressed bytes are not automatically a compatibility
failure or proof of equivalence. Custom codec/interpreter upkeep is not
justified by present evidence. No custom archive format is proposed.

## Immutable public sources

| Source | Revision and relevant locations |
|---|---|
| Standalone dependency pins | [`b498734a...`, downloads.json:481-498](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/pythonbuild/downloads.json#L481-L498) |
| Windows dependency override / codec selection | [`b498734a...`, build.py:433-448](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/cpython-windows/build.py#L433-L448), [1467-1474](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/cpython-windows/build.py#L1467-L1474) |
| zlib ARM CRC guards and instructions | [`da607da7...`, crc32.c:87-112](https://github.com/madler/zlib/blob/da607da739fa6047df13e66a2af6b8bec7c2a498/crc32.c#L87-L112), [490-550](https://github.com/madler/zlib/blob/da607da739fa6047df13e66a2af6b8bec7c2a498/crc32.c#L490-L550) |
| CPython Windows codec compilation | [`4061bc4c...`, pythoncore.vcxproj:645-658](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/PCbuild/pythoncore.vcxproj#L645-L658) |
| Mac target / system libz normalization | [`b498734a...`, targets.yml:72-123](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/cpython-unix/targets.yml#L72-L123), [build-cpython.sh:846-852](https://github.com/astral-sh/python-build-standalone/blob/b498734a5791d0e6786695a226fd398a41c6f7f6/cpython-unix/build-cpython.sh#L846-L852) |
| Published Apple ARM CRC assembly / definition | [`06673bf7...`, crc32lt_arm64.s:1-10](https://github.com/apple-oss-distributions/zlib/blob/06673bf7cb4066003fd14a0b87085c05739fc4ac/AddOn/ZAssembly/crc32lt_arm64.s#L1-L10), [zlib.xcconfig:20-22](https://github.com/apple-oss-distributions/zlib/blob/06673bf7cb4066003fd14a0b87085c05739fc4ac/zlib.xcconfig#L20-L22); not proven deployed CI revision |
| gzip raw deflate / separate CRC | [`4061bc4c...`, gzip.py:233-237](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/gzip.py#L233-L237), [320-333](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/gzip.py#L320-L333) |
| Stock Windows zlib default | [`4061bc4c...`, python.props:81-83](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/PCbuild/python.props#L81-L83) |

Existing local evidence, relative to `Generated Files\arm-build`:
`results\profile-01\sdist.txt:1-21`, `wheel.txt:39`,
`profile.json:2-16`; `profiles\sdk-validation\profile.json:23-31,162-168,306-312`;
`toolchain\PROVENANCE.md:7-32`. These remain historical evidence, not a new
matched Windows/Mac result.
