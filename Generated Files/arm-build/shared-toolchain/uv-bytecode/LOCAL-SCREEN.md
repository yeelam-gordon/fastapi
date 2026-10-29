# P22 RANK2 supported-policy screen: reject and stop

2026-10-29. One bounded FastAPI-only local screen completed; **do not adopt
`PYTHONDONTWRITEBYTECODE=1` as a build-performance practice on this evidence**.
The source-only upstream-default no-go remains unchanged.

## Result

| Arm | Policy in the uv child environment | Five timed walls, seconds | Median | Range |
|---|---|---|---:|---|
| A | `PYTHONDONTWRITEBYTECODE` explicitly absent | 5.784675, 6.164161, 5.954843, 5.950318, 5.780983 | **5.950318** | 5.780983–6.164161 |
| B | `PYTHONDONTWRITEBYTECODE=1` | 5.815331, 5.574931, 5.981183, 6.060927, 6.013402 | **5.981183** | 5.574931–6.060927 |

`PYTHONPYCACHEPREFIX` was absent in **both** arms. No global environment setting
was modified. B's median was **0.030864 s / 0.519% slower**.

| Pair | Fixed order | A minus B, seconds (positive favors B) | B saving |
|---|---|---:|---:|
| 1 | A/B | -0.030657 | -0.530% |
| 2 | B/A | +0.589230 | +9.559% |
| 3 | A/B | -0.026340 | -0.442% |
| 4 | B/A | -0.110609 | -1.859% |
| 5 | A/B | -0.232419 | -4.020% |

Only **1/5** pairs favored suppression; distributions overlapped. The runner
declared before samples that a candidate required >=5% median improvement and
at least 4/5 positive paired savings. Both gates failed. The isolated favorable
pair is retained, not selected as the result.

One disclosed warmup per arm, A then B: **6.537635 / 7.039414 s**, excluded.
All twelve commands succeeded; no retries, replacements, sample reductions,
profiling or instrumentation inside timed children.

## Workload, controls and receipts

- Source: FastAPI 0.162.0, immutable
  `79cab5bed28b24d92c185d236feb33f5783dfeb3`; existing `source-fastapi` worktree
  read-only. `git -c core.autocrlf=false archive` produced a canonical tar whose
  PAX commit was checked. All 3,233 source files (35,440,623 bytes) have hashes
  and Git archive modes in `source-manifest.json`.
- Stock uv **0.13.6**, `329bf9448`, native `aarch64-pc-windows-msvc`.
  Existing verified C: binary copied and checked against the prior SHA-256.
- Managed CPython **3.13.15**, MSVC 19.44, verified `win-arm64` / `ARM64`.
  Existing base interpreter used directly, not the older MSI or a caller venv.
  Executable and `python313.dll` hashes are recorded.
- Stock **pdm-backend==2.5.0**, wheel SHA-256 checked against the existing
  receipt; explicit build constraint plus a wheelhouse containing only that
  existing wheel. No SDK, private backend patch, selector or changed lifecycle.
- Private C: root:
  `C:\fastapi-arm-build-lab\uv-bytecode-ba943ace3993`.
  C: was observed healthy **NTFS** using `Get-Volume`. Runtime, wheelhouse,
  dependency cache, tools, source, outputs and all TEMP/TMP/TMPDIR paths used
  by actual builds were on C:. Q: held only orchestration/evidence and the
  read-only archive source/oracle outside timers. No protection, trust,
  permissions or security settings were changed.
- A new source/output/temp directory for **every** warmup/sample was prepared
  and byte-checked outside the timer. The same dedicated local dependency cache
  was warmed by the two disclosed warmups and retained, not purged. OS caches
  were uncontrolled. Other C: campaigns were reported stopped by the caller.
- Inherited `UV_*`, `PIP_*` and `PYTHON*` variables were removed from the common
  child environment; `PYTHONNOUSERSITE=1` was common. A separately constructed
  per-child mapping changed only suppression between arms. Paths differ only
  to provide required fresh sample isolation. No `os.environ` mutation.
- Timer begins immediately before spawning stock uv and ends after it exits:
  normal isolated environment creation/install, hook imports, sdist then
  wheel-from-sdist, and uv cleanup are charged. Source preparation and artifact
  verification are outside. No process CPU or preparation-inclusive claim.

Each exact argv/cwd/environment policy is retained in
[results.json](screen-ba943ace3993/results.json). Command family:

```text
uv --no-config --offline --cache-dir <C-cache> build <fresh-C-source>
  --python <existing-C-managed-python> --no-python-downloads --no-index
  --find-links <C-wheelhouse> --build-constraints <C-constraint>
  --out-dir <fresh-C-output> --no-create-gitignore
```

Default sdist-to-wheel plan and uv's normal per-stage build isolation remained
intact. Offline/no-index/no-download policy prevented new acquisition; only the
normal ephemeral backend installation from the existing wheel occurred.
There was no package provisioning, CI, push, PR or upstream contact.

## Independent correctness verdict: payload pass, known modes FAIL

The existing independent Mac standard-build oracle was inventoried with the
existing `candidate\validate.py` **verification helper only**; no candidate
packager was imported or executed. Oracle archive hashes, validator hash, full
oracle inventory and every sample's complete inventory are retained. The
oracle's exact member/payload/metadata agreement establishes its applicability
to this source; it is not relabeled as a newly built 79cab Mac measurement.

For **all 12 outputs**, including warmups:

- All **1,269 sdist / 65 wheel** members, every payload hash/size, generated
  metadata, full wheel permission/type fields and wheel RECORD hash/size/coverage
  checks matched the oracle.
- Full tar mode/uid/gid/uname/gname/size checks matched **except exactly five
  script modes**: `scripts/format.sh`, `lint.sh`, `test-cov-html.sh`,
  `test-cov.sh`, `test.sh`. Oracle: `0755`; both stock Windows arms: `0644`.
  Thus **strict oracle mode correctness FAILS in both arms**. No permission
  normalization, repair or waiver occurred.
- A and B complete inventories matched the first normal Windows warmup exactly.
  Existing normal-build payload/mode/metadata/RECORD semantics **did not regress**.
  Every original source file's bytes remained unchanged.

Archive timestamps/compression byte identity are not equivalence requirements;
artifact SHA-256 values are nevertheless recorded. No installed-wheel smoke or
FastAPI tests were requested/run. This is not blanket correct cross-OS parity.

## Uncertainty and disposition

- **High:** this fixed local command sample, exact inputs/policy, successful
  payload/metadata/RECORD checks, equal Windows semantics and the explicit
  five-file mode failure.
- **Medium:** rejection as a useful practice for this warm-cache FastAPI workload;
  small sample, shared host and uncontrolled OS caches prevent a durable
  performance estimate. No evidence supports even a meaningful positive gain.
- **Low / unmeasured:** actual ephemeral import `.pyc` counts, import CPU,
  scanner/MDE activity or causality, cold builds, other backends, Mac effects,
  hosted CI, tests and physical hardware.

Stop here: no cross-backend checks or CI are justified by this failed screen.
A Windows-only conditional practice could be useful in principle, but this
screen does not establish one. If independently justified future work reopens
the question, Mac must test both policies and retain its best correct setup,
not be forced to use suppression. No upstream change belongs in review on
these results; supported policy already exists and measured value is absent.

All action/evidence is in this owned directory. Binary/source/output/temp/cache
scratch remains outside Git in the unique owned C: root; previous receipts and
prepared toolchains were not overwritten. The orchestrator is `screen.py`;
this report records its single execution, not a new benchmarking framework.
