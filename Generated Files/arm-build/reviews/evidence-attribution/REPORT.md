# Independent evidence / attribution acceptance review

**Verdict: accept the bounded evidence, not release adoption or goal completion.**
One medium-priority synthesis defect remains: the live proposal table schedules
already-completed investigations and omits the strongest current small proposal.
No new high-severity experimental defect was established in this bounded pass.

Reviewed branch: `review/arm-evidence-attribution`; source snapshot:
`bfc306726db5727d6a358e85630ced44aa4aa4e2`. Paths below are relative to
`Generated Files` unless explicitly repository-relative. Review commit SHA is
the commit containing this report, not a purported measured-source revision.

## Consequential findings and dispositions

### EA-001 — Medium: actionable synthesis is behind retained evidence

**Location:** `INVESTIGATION-AND-PROPOSALS.md:13,27-29`.
**Observed:** P11 still calls its follow-up running and directs investigation of
the old C: stall; P12 remains a hypothesis; P13 still says measuring and heads
execution priority. **Expected:** distinguish historical controls from completed
results and rank the next unresolved acceptance gate, not rerun these screens.

**Proof:** `arm-build/filesystem/c-vs-q/followup/REPORT.txt:11-40` and raw
`evidence.json` show real uv 5.0136 s, corrected full 6.2751 s and selective
3.3004 s medians; the earlier sdist stall did not recur. This does not identify
what removed it. `arm-build/frontends/REPORT.md:9-19` records nine completed
isolated builds. `arm-build/filesystem/stdlib-ops/REPORT.txt:12-45` records
completed attribute/prefetch controls and a medium-maintenance proposal.
The independent receipt checker reproduces these medians.

**Confidence: high. Disposition: accept defect; root integration required.**
Update P11-P13 and add/rank prefetch, retaining the old samples as history.
Next gate is supported release-frontend integration and applicable optimized
Mac comparison, not another completed screening matrix. Do not rank the
no-isolation follow-up and isolated frontend matrix as interchangeable samples.

### EA-002 — Workload and credit boundaries: accept; reject broader inference

**Locations:** `arm-build/prior-work/hobl/AUDIT.md:5-43`,
`arm-build/frontends/REPORT.md:7,85-111`;
repository `.github/workflows/publish.yml:34-37`.

**Observed/source proof:** pinned HOBL Windows source lines 353-355, 378-380,
401-403 and 419 time legacy build, modern uv build and tests separately, then
sum them. Its application harness lines 427-431 instead sums the startup,
import/OpenAPI and app-test medians, excluding sync/reload. The audit correctly
retains the predecessor build-plus-tests distinction and Mac test-command
change. HOBL FastAPI 0.119.1 / Python 3.12.10 is not our 0.162.0 / 3.13.15.
The separately supplied private numerical table remains unclassified: it was
**not opened, reproduced or used in arithmetic** here. RICE assumptions are not
measured outcomes; this pass does not independently verify its arithmetic.

Current publish already runs `uv build`. The local A/B/C comparison establishes
tool/workload differences, not a newly discovered repository configuration fix.
Actual retained build-1.6.1 verbose logs and the runtime probe support external
pip with `--no-compile`, `with_pip=False`, no virtualenv and no ensurepip on A's
observed path. That does not establish older HOBL frontend behavior.

**Confidence: high on checked boundaries; low on missing historical outcomes.**
**Disposition:** accept source audits and nine local observations; reject
reproduction, new-fix credit or explanation of the supplied table. Next gate:
source-matched historical inputs only if that historical metric becomes the
explicit target; do not silently substitute package building for application
setup, tests or reload.

### EA-003 — Interpreter optimization: accept source conclusion, reserve exact bytes

**Locations:** `arm-build/toolchain/RESEARCH.md:9-21`,
`arm-build/toolchain/PROVENANCE.md:5-39`.

**Proof:** independently fetched pinned standalone Windows builder lines
1630-1640 and 1686-1712 implement instrumentation, training and PGUpdate.
CPython `v3.13.15` MSI wrapper lines 96-103 passes PGO to x64 but not ARM64;
line 253 documents that wrapper default. These are different distributions.
Published metadata described by PROVENANCE supports Windows standalone PGO
versus Mac PGO+LTO; the Windows label does not demonstrate absent LTCG.
This review did not redownload/execute the full release archives, and the old
CI lacks executable hashes tying each executed binary to those archives.

**Confidence: high on inspected recipes, medium on exact executed distribution
mapping, low on compiler/SIMD performance causality. Disposition:** accept the
rejection of a blanket “unoptimized Windows” premise; reject a pure-PGO speedup
claim or exact-binary certification. Next gate: runtime/download fingerprints
and a relevant CPU-bound stage, before considering expensive toolchain work.
Do not subtract stock follow-up samples from managed stdlib samples.

### EA-004 — Distinct mechanisms and exact prior credit: accept

**Locations:** `PRIOR-WORK.md:9-23`,
`arm-build/prior-work/bootstrap/AUDIT.md:12-38`,
`arm-build/prior-work/uvicorn/AUDIT.md:5-35`,
`arm-build/filesystem/stdlib-ops/REPORT.txt:95-100`.

Pinned public pip source lines 420-424 gates bounded forced bytecode threads
to Windows; lines 688-696 gates compilation itself. That is not our portable
PDM payload-read overlap. Pinned ensurepip lines 167-193 attempt a bundled-wheel
hardlink with copy fallback without a Windows gate. Its 3.12 lineage is not a
literal 3.13 patch; shared Mac potential must remain explicit. Uvicorn's stacked
reload mechanisms belong to runtime, not package building. Inline source/test
audits establish inspected behavior, **not passing execution or measured speed**.

Public commit metadata independently checked for:

| Contribution | Original author / recorded co-author | Pinned commit |
|---|---|---|
| pip bytecode threads | Clint Rutkas / Copilot App | `d86a728fdcfa2f694149a466c745115af476ee11` |
| ensurepip hardlink POC | Clint Rutkas / Copilot App | `0e522c49773a4be778a843d3a0251cae3b9d34c7` |
| Uvicorn graceful reload | Clint Rutkas / Copilot App | `58779399365e7a79b5cbccaf9bb67fc25b73a9a6` |
| Uvicorn dedup | Clint Rutkas / Copilot App | `70ab5bafa84ac0f2b6520fdc223bd3a7831580f6` |
| HOBL workload separation | Clint Rutkas / Copilot App | `a428df4efeeff36cadb00f8f95f90ef97cc12b6f` |

**Confidence: high. Disposition:** accept existing credit, explicitly extend it
to HOBL's named authors above. Reproduction/integration is not authorship.
No novelty claim follows merely from a different use of threads.

### EA-005 — Timing, causality and CI: accept bounded claims only

**Locations:** `arm-build/frontends/REPORT.md:109-111`,
`arm-build/filesystem/stdlib-ops/REPORT.txt:24-31,78-100`,
`arm-build/filesystem/c-vs-q/followup/REPORT.txt:32-63`,
`arm-build/CI.md:1-3,42-59`.

The checker independently recomputes 55.581% A-to-C isolated-command reduction
and 27.690% stdlib combined reduction, compares all 12 timed stdlib manifests
to the retained full reference, and all nine frontend manifests/modes to their
same-Windows reference. It confirms the nine frontend outputs still record
five Mac sdist mode failures; uv follow-up strict passes are 0/3, versus 3/3 for
each corrected control. These are retained-manifest checks, not archive or
wheel-RECORD re-execution.

Prefetch leaves diagnostic opens at 1,617. Noattrs removes 64 chmod and 64 utime
audit events, not proven kernel calls or scanner counts. Stdlib process CPU
medians actually increase from 1.875 s sequential to 2.094 s threaded with attrs
held fixed; lower wall time is not CPU saving. Frontend launcher CPU excludes
descendants and cannot supply total workload CPU. Protected-process CPU and
scanner contribution remain unknown, not zero. C:/Q: changes storage/filesystem
conditions together; neither it nor the non-reproduced stall identifies MDE.

Retained job receipts still support exactly the documented two-run sequence:
40814042898 Windows success / Mac failure; 40814588064 both successes, while its
strict comparison receipt remains `failed`. This verifies consistency of the
retained record, not a live assertion that GitHub has no later run. No GitHub
run polling or dispatch was performed.

**Confidence: high on retained arithmetic/status, medium on three-trial warm
ordering, low on generalized or causal explanations. Disposition:** accept
local descriptive gains; reject scanner attribution, CPU savings, accepted
cross-platform parity, or physical-device conclusions.

### EA-006 — Prefetch acceptance: worthwhile medium-maintenance candidate only

**Location:** `arm-build/filesystem/stdlib-ops/REPORT.txt:33-64`.
All three paired prefetch deltas are positive for either attribute setting.
The bounded reader plus existing stdlib serialization is meaningfully smaller
than a custom format writer; the private PDM override still creates real
maintenance/API cost. Attribute skipping has smaller benefit and must retain
the regular-0644 disposable-input guard and final full modes.

**Confidence: medium on benefit; high on retained validation records.**
**Disposition:** accept as a proposed next gate, not release implementation
approval. Prefer a supported/upstream seam; include fresh metadata, imports,
reads, extraction and cleanup in integration timing. Apply common options to
Mac too, count setup separately, and compare best validated configurations via
Windows/Mac ratio. Small shared gains alone do not justify custom-packager
maintenance. Functional implementation review belongs to the separate worker.

## Verification and limits

`verify_receipts.py` passed; `receipt-verification.json` retains recomputed
values and SHA256 fingerprints of its inputs. `SOURCE-CHECKS.json` records the
bounded pinned-public-source checks. The six passing stdlib tests were read
from their retained log, **not rerun**. No benchmark, CI, subagent, push,
producer change, ETL, private supplied table or security-setting access occurred.

Goal remains open: equivalent optimized live Mac timing, release integration,
durable hosted parity and physical hardware results are unestablished. Missing
verification is an acceptance boundary, not permission to call partial work
completion.
