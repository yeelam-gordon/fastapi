# P25 staged screen: reject current form; Phase B not started

2026-10-29. **Phase A failed its predeclared gate. Stop; no full build.**
The identity-fixed 13-line source prototype is unchanged. No tuning or
replacement repeats were performed. This is a micro/toolchain source finding,
not evidence of standard-command build improvement or Windows/Mac parity.

## Fixed design

`micro_screen.py` uses only builtin `timeit` for timing, in a fresh native ARM64
CPython 3.13.15 child with source-prefix pathlib and origin/hash assertions.
Candidate source SHA-256 is
`ffdec1568d6c4f6826ecfb8dfeaa77f9647ebc90598766ab353787927b019b3c`.
Baseline method AST comes directly from immutable Git commit
`4061bc4c35f7c26f25264666d4ba083b93d2f6f9`; complete baseline source hash is
`0530b4186ec5845e000bedf5817ff1ac970b9a39a6891ba6789a1776abdea42b`.
The method is compiled into a separate globals dictionary; no runtime method
is replaced. Both arms are comparably unbound calls through the same invocation
wrapper, including result stringification or ValueError handling.

Predeclared cases: stock WindowsPath, PureWindowsPath and PurePosixPath, each
with shallow/deep/equal/root success, nonancestor error, walk_up and subclass
fallback. Deep paths have 16 intermediate components. Inputs are constructed
outside timing and reused identically in both arms. One warm call per arm/case
also checks outcome agreement. Each case then runs **10,000 calls per repeat,
five fixed pairs ordered AB, BA, AB, BA, AB**, with no replacements or retries.
timeit disables GC normally. These are deliberately **hot-cache** small cases,
not representative whole builds; shared-host/cache uncertainty remains.

Gate was >=10% median fractional saving across the eight Windows success
cases, **and no >20% regression in any Windows success or any fallback case**.
The extra equal-path safety gate prevents an aggregate of deep-path wins from
concealing a common success regression. All thresholds and cases were in the
script and initial result file before timing.

## Actual results

Microseconds/call: median [min, max] across five repeats. A = baseline;
B = reviewed candidate. Positive saving favors B. Rounding is display-only;
all raw timeit totals and exact medians/ranges are in `MICRO-RESULTS.json`.

| Class | Case | A, us/call | B, us/call | Saving |
|---|---|---|---|---:|
| WindowsPath | shallow | 6.185 [6.179, 6.194] | 3.337 [3.336, 3.352] | +46.05% |
| WindowsPath | deep | 48.374 [48.357, 48.455] | 3.530 [3.528, 3.535] | +92.70% |
| WindowsPath | equal | 2.383 [2.379, 2.408] | 3.193 [3.184, 3.206] | **-34.03%** |
| WindowsPath | root | 50.623 [50.572, 50.831] | 3.463 [3.460, 3.469] | +93.16% |
| WindowsPath | nonancestor | 8.018 [8.003, 9.185] | 9.745 [9.738, 11.033] | **-21.54%** |
| WindowsPath | walk_up | 18.396 [18.373, 19.585] | 18.528 [18.525, 18.559] | -0.72% |
| WindowsPath | subclass | 6.523 [6.516, 6.536] | 7.216 [7.213, 7.223] | -10.63% |
| PureWindowsPath | shallow | 5.773 [5.760, 5.789] | 2.955 [2.949, 2.972] | +48.82% |
| PureWindowsPath | deep | 44.617 [44.603, 44.687] | 3.148 [3.144, 3.160] | +92.94% |
| PureWindowsPath | equal | 2.164 [2.161, 2.165] | 2.781 [2.777, 2.783] | **-28.50%** |
| PureWindowsPath | root | 46.686 [46.650, 46.774] | 3.084 [3.082, 3.087] | +93.39% |
| PureWindowsPath | nonancestor | 7.614 [7.573, 7.658] | 9.096 [9.078, 9.154] | -19.47% |
| PureWindowsPath | walk_up | 16.979 [16.972, 17.010] | 17.124 [17.107, 17.132] | -0.85% |
| PureWindowsPath | subclass | 6.012 [6.008, 6.025] | 6.668 [6.659, 6.670] | -10.91% |
| PurePosixPath | shallow | 5.678 [5.649, 5.715] | 2.745 [2.739, 2.780] | +51.65% |
| PurePosixPath | deep | 43.534 [43.477, 43.636] | 2.900 [2.898, 2.929] | +93.34% |
| PurePosixPath | equal | 2.162 [2.161, 2.168] | 2.606 [2.598, 2.609] | -20.53% |
| PurePosixPath | root | 45.674 [45.524, 49.189] | 2.829 [2.821, 2.839] | +93.81% |
| PurePosixPath | nonancestor | 7.415 [7.399, 7.490] | 8.780 [8.765, 8.802] | -18.42% |
| PurePosixPath | walk_up | 16.780 [16.773, 16.816] | 16.903 [16.880, 16.956] | -0.74% |
| PurePosixPath | subclass | 5.874 [5.865, 5.939] | 6.574 [6.569, 6.587] | -11.91% |

Median fractional saving across Windows successes is 70.76%, **not a workload
weighted speedup**. The gate nevertheless fails on both Windows equal cases
and WindowsPath nonancestor fallback. Existing baseline equality is already
cheap; the candidate performs extra guard/format work before reaching an
equivalent result. No threshold was relaxed to retain the deep-path wins.

## Phase B and maintainer disposition

**Not executed.** No C: runtime copies, managed-source-byte matching, uv Python
selection checks, warmup builds, five standard-command pairs or new artifact
comparisons were started. The existing uv-bytecode screen was read for
preparation only. No packages, network acquisition or C: writes were needed.
Existing five stock Windows script-mode failures remain unresolved prior
evidence; they were not re-tested, repaired or waived here.

The common allocation lead remains plausible, but this exact prototype fails
its cost gate. Do not adopt, request CI or extrapolate micro improvements to
build savings. No second design/tuning pass is authorized. Barney Gale's
python/cpython#111431 improvements remain unchanged and credited in REPORT.md.

**Confidence:** high in recorded measurements/gate failure and unchanged source
hash; medium in generalizing the regression beyond this hot-cache case set;
low/unmeasured for end-to-end benefit, fallback workload mix, Mac results and
parity. PurePosixPath runs on Windows, not native macOS.

Exact command from the owned worktree:

```powershell
python -I -S -B 'Generated Files\arm-build\shared-toolchain\pathlib-relative\micro_screen.py' *> 'Generated Files\arm-build\shared-toolchain\pathlib-relative\micro-screen.log'
```

`MICRO-PROVENANCE.json` records command, runtime executable/DLL hashes, source
and patch hashes, and raw evidence hashes. No CPU/scan claims, protection
changes, installed-runtime/FastAPI mutation, compiler build, CI, upload,
push/PR, owner contact or delegation occurred.
