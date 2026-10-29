# P25 v2 staged cost screen

2026-10-29. Diagnostic only: no adoption, CI or parity recommendation.
V1 rejection, its original 210 timings and all gates remain unchanged.

## Phase A: PASS, one identical predeclared screen

`v2_micro_screen.py` differs from the v1 script in **only two strings**:
reviewed candidate source hash and new results filename. Cases, 10,000 calls,
five fixed paired orders AB/BA/AB/BA/AB, warm calls, invocation wrapper,
thresholds and hot-cache/GC policy are unchanged. Baseline is the exact pinned
method compiled from Git AST, candidate is comparably unbound; no monkeypatch
or timed construction asymmetry. Fresh source-prefix native ARM64 3.13.15 child.
No repeated/tuned screen and no pooling with v1.

All **21 cases / 210 raw timings** are in `V2-MICRO-RESULTS.json`.
Per-case medians/ranges and five A-minus-B deltas are also retained in
`V2-MICRO-SUMMARY.json`. Positive saving favors candidate. Selected medians
below are microseconds/call [minimum, maximum] across five repeats:

| Class | Case | Baseline | V2 | Saving |
|---|---|---|---|---:|
| WindowsPath | shallow | 6.255 [6.247, 6.290] | 2.453 [2.447, 2.478] | +60.78% |
| WindowsPath | deep | 48.278 [48.240, 48.525] | 2.621 [2.616, 2.622] | +94.57% |
| WindowsPath | equal | 2.387 [2.382, 2.415] | 1.731 [1.723, 1.773] | +27.48% |
| WindowsPath | root | 50.610 [50.598, 50.866] | 2.535 [2.531, 2.539] | +94.99% |
| WindowsPath | nonancestor | 8.056 [8.023, 8.076] | 1.609 [1.605, 1.612] | +80.03% |
| WindowsPath | walk_up | 18.404 [18.395, 18.425] | 18.482 [18.435, 18.487] | -0.42% |
| WindowsPath | subclass | 6.553 [6.539, 6.655] | 6.679 [6.655, 6.722] | -1.92% |
| PureWindowsPath | equal | 2.181 [2.180, 2.190] | 1.506 [1.504, 1.551] | +30.94% |
| PureWindowsPath | nonancestor | 7.609 [7.604, 7.622] | 1.592 [1.592, 1.592] | +79.08% |
| PurePosixPath | equal | 2.211 [2.209, 2.220] | 1.511 [1.510, 1.513] | +31.65% |
| PurePosixPath | nonancestor | 7.501 [7.481, 7.570] | 1.477 [1.475, 1.478] | +80.31% |

Median fractional saving across eight Windows successes: **78.40%**, a
case-set summary, **not workload-weighted build improvement**. No Windows
success or any fallback exceeded the unchanged 20% regression safeguard.
Maximum observed fallback regression was WindowsPath subclass at 1.92%.
Both unchanged gates passed, allowing the specifically authorized Phase B.
PurePosixPath measurements here are Windows-hosted, not Mac timings.

Micro command from the owned worktree:

```powershell
python -I -S -B 'Generated Files\arm-build\shared-toolchain\pathlib-relative\v2_micro_screen.py' *> 'Generated Files\arm-build\shared-toolchain\pathlib-relative\v2-micro-screen.log'
```

## Phase B controls

Reused the existing uv-bytecode stock screen as `v2_build_screen.py`, retaining
canonical source extraction, stock command, five-pair decision rule, artifact
validator and independent oracle. The only build-treatment change is private
runtime selection, not backend/SDK or bytecode policy.

Actual managed `_local.py` was hashed **before copying** and exactly matched
`0530b4186ec5845e000bedf5817ff1ac970b9a39a6891ba6789a1776abdea42b`;
no newline normalization or substituted baseline.
Candidate source is reviewed SHA-256
`b6616ee0240d1ced9e2ff3f02dcfbbe0f30e7c5d8b751e6f9f986cce4f4a1e3e`.
Independent full runtime copies use copy2, no hardlinks. Before probing/builds,
every copied file has link count one, and their full-file hash inventories
differ **only** at `Lib/pathlib/_local.py`. Default subsequent bytecode cache
writes are normal derived effects, not suppressed or manually shared.

Both uv-selected private interpreters are probed outside timers for executable,
ARM64 platform, version, base prefix, pathlib origin/source hash and loaded
`python313.dll` path/hash. Exact uv-find/probe argv and receipts are in results.
This is not instrumentation inside timed isolated backend children: their
runtime is constrained by each standard build's explicit `--python` argument.

Stock uv 0.13.6 and OFFICIAL PDM 2.5.0 wheel hashes are checked against existing
verified offline receipts. Original FastAPI commit
`79cab5bed28b24d92c185d236feb33f5783dfeb3` is canonically archived; all source
file payload hashes/modes are recorded. No modified manifest, selector, custom
backend or network acquisition. Both arms explicitly unset
PYTHONDONTWRITEBYTECODE/PYTHONPYCACHEPREFIX; PYTHONNOUSERSITE is common.

C: is recorded healthy NTFS. Runtime, executable, DLL, source, backend wheel,
uv binary, dependency cache, output and TEMP/TMP/TMPDIR used by actual builds
are in one unique owned C: child; protection/configuration is unchanged.
Fresh source/output/temp for each warmup and timed sample, source hashes checked
outside clocks. One untimed warmup per arm, then five fixed pairs
AB/BA/AB/BA/AB; no replacement samples/retries. Full uv process wall includes
normal two-stage isolation, backend installation/imports and cleanup. Source
prep, runtime copying/probes and artifact verification are outside clocks.

Standard command family (each exact argv/cwd/policy is retained):

```text
uv --no-config --offline --cache-dir <owned-C-cache> build <fresh-C-source>
  --python <owned-C-runtime-A-or-B-python.exe> --no-python-downloads
  --no-index --find-links <owned-C-wheelhouse>
  --build-constraints <owned-C-constraints> --out-dir <fresh-C-output>
  --no-create-gitignore
```

Orchestrator command from the owned worktree:

```powershell
python -I -S -B 'Generated Files\arm-build\shared-toolchain\pathlib-relative\v2_build_screen.py' *> 'Generated Files\arm-build\shared-toolchain\pathlib-relative\v2-build-screen.log'
```

## Phase B actual result: completed, advancement gate FAIL

Evidence directory: `v2-build-743193478a3e\`.
Owned C: child: `C:\fastapi-arm-build-lab\pathlib-v2-743193478a3e`.
Both full runtime copies contain 3,373 initial files; only reviewed `_local.py`
differs. Their executable SHA-256 is
`383d0ff495b7a4903426037fa003f72963aaebd4f1aa3cd08a22895421c703bd`;
`python313.dll` SHA-256 is
`1eca9e2e85bb5ea49ad6452b2603272ff8245357bf98a41bdb96f35c1479511f`.
The managed build runtime reports 3.13.15, Sep 29 2026, MSVC 19.44 ARM64;
this is distinct from the installed runtime used for Phase A. No measurements
are pooled across them. The A/B build binaries and all initial non-treatment
bytes are identical within this campaign.

| Arm | Five full uv command walls, seconds | Median | Range |
|---|---|---:|---|
| A baseline | 5.631065, 6.067898, 6.016315, 5.768825, 5.626481 | **5.768825** | 5.626481–6.067898 |
| B v2 | 5.706112, 5.494239, 5.923309, 5.607615, 5.412191 | **5.607615** | 5.412191–5.923309 |

| Pair | Fixed order | A minus B, seconds | B saving |
|---|---|---:|---:|
| 1 | AB | -0.075047 | -1.333% |
| 2 | BA | +0.573659 | +9.454% |
| 3 | AB | +0.093006 | +1.546% |
| 4 | BA | +0.161210 | +2.795% |
| 5 | AB | +0.214290 | +3.809% |

One untimed warmup each, A then B: **7.270779 / 5.796581 s**, excluded.
All twelve standard commands succeeded and validated; no unexpected failure,
retry, replacement, extra build or instrumentation inside timed children.
The existing runner's predeclared full-build rule required >=5% median
improvement and at least 4/5 positive paired savings. **4/5** pairs favored v2,
but median improvement was only **0.161210 s / 2.7945%**, with overlapping
ranges, so the rule returns **reject**. Do not select the 9.45% pair or infer
that a 78.40% micro case-set saving means a comparable full-build gain.

## Full artifact verdict: same-Windows PASS; independent strict modes FAIL

All twelve outputs have full Windows inventory equality to the first baseline:
members, payload SHA-256, metadata, modes and wheel RECORD checks match.
Every fresh source's original payload hashes remain unchanged.
Raw artifact-file hashes, per-output complete inventories, independent Mac
oracle inventory and oracle artifact hashes are retained. Compressed container
bytes need not share one hash because incidental timestamps are not payload
semantics; member-level equivalence is checked independently.

Against the independent Mac oracle, **strict pass remains false in all twelve
outputs**, solely for these stock Windows source-distribution modes:

* `fastapi-0.162.0/scripts/format.sh`
* `fastapi-0.162.0/scripts/lint.sh`
* `fastapi-0.162.0/scripts/test-cov-html.sh`
* `fastapi-0.162.0/scripts/test-cov.sh`
* `fastapi-0.162.0/scripts/test.sh`

Each is expected 0755, actual 0644. These failures are retained explicitly,
not repaired or waived; there are no other oracle payload/member/metadata/
RECORD differences. This is not a strict cross-platform artifact acceptance.

## Confidence, receipts and stop

**High:** fixed protocol completion, raw timings, source/binary identities,
same-Windows artifact verdict, known independent mode failures and failed
predeclared advancement gate. **Medium:** a modest end-to-end benefit may be
real on this host; one small paired campaign and overlapping ranges do not
establish its general size. **Low/unmeasured:** cross-project benefit, native
Mac timing, setup-inclusive totals, CPU/scan attribution and parity.

Source semantics remain a credible small upstream lead, but this bounded cost
screen is insufficient to recommend adoption or automatically spend CI. The
five mode failures and maintainer value/compatibility gates still apply.
No further design revision, timing campaign, CI, upload, PR or owner contact
is authorized. Barney Gale's existing python/cpython#111431 improvements
remain credited and unchanged; this work does not claim them.

`V2-STAGED-PROVENANCE.json` hashes every new build receipt and top-level screen
artifact, records exact commands, unchanged case/gate verification, source patch
provenance and post-run source/executable/DLL integrity checks. Root-owned
`v2-root-modules.json` was deliberately not overwritten, deleted or committed.
V1 source, code, logs, 210 timings and archive hashes remain unchanged.
V1 text-artifact identity is checked against committed Git blobs, not
working-tree CRLF conversions. An initial finalization-only raw-file assertion
tripped on `.gitattributes`; the committed-blob policy used by the earlier
archive proof resolves that distinction. No timing, sample or validation was
repeated or replaced as a result.
Exact executed script bytes are additionally retained under `v2-executed-code\`
with text conversion disabled. Runnable top-level scripts and this report use
Git's canonical LF text hashes; their Windows working copies may use CRLF.
Both executed-byte hashes and canonical committed hashes are recorded, avoiding
an EOL-only mismatch without changing or rerunning the measured code.
