# Public source receipts

Audit date: 2026-10-29. Public GitHub REST reads through `gh api`; no source
execution, install, benchmark, CI dispatch, push, PR or image upload.
Queries used only repository names, paths and source metric identifiers.
No supplied numerical measurements were used as search terms or copied here.

Read-only local context:
- Root `Generated Files\MEASUREMENT-BOUNDARIES.md`.
- Root `Generated Files\arm-build\prior-work\hobl\AUDIT.md`.
- Root `Generated Files\PRIOR-WORK.md` (the ledger is here, not inside `hobl`).
- Root existing `Generated Files\arm-build\CI.md` and
  `.github\workflows\arm-build-diagnostics.yml` for coverage, not execution.

Public API scope:
- `repos/crutkas/HOBL`: fork parent/source is `microsoft/HOBL`; default is main.
- Recursive blob-path listings at the feature pin and upstream main pin below;
  focused inspection of report/dashboard/result/UI/export paths.
- Raw pinned contents: FastAPI run scripts/scenario wrapper;
  `scenarios/common/{run_report,study_report}.py`, `tools/run_report.py`;
  `utilities/open_source/{gen_study_report,gen_study_report_json,rollup_metrics_json,gen_run_report2}.py`;
  report weighting JSON and README. No matching cross-OS elapsed/percentage
  renderer was identified in this bounded scope. Excel/report formatting and
  power-weight percentages are not evidence of the supplied row's formula.

| Repository/revision | Windows FastAPI script blob | JSON study exporter blob | JSON rollup blob |
|---|---|---|---|
| crutkas/HOBL feature `5e9e1ae540a8099485e30e2044ceb68d29d982e6` | `a9f75d54edfc495737a5a83cd0cc22fa2f685298` | `f7184d6f0f595e8609bdd98b93107abaa802227c` | `89e3c6e9292a774e3196a75843e424a669ee0838` |
| microsoft/HOBL main `df120528374c0a5de5cb5a526175973d1ea2b53f` | `30132f5d486db88393af27f9fff1a039a11f4969` | `f7184d6f0f595e8609bdd98b93107abaa802227c` | `89e3c6e9292a774e3196a75843e424a669ee0838` |
| crutkas/HOBL main `25801a08d0749bdac122fab688fd28a0faadbba9` | `30132f5d486db88393af27f9fff1a039a11f4969` | `f7184d6f0f595e8609bdd98b93107abaa802227c` | `89e3c6e9292a774e3196a75843e424a669ee0838` |

Main heads were resolved via `repos/{owner}/HOBL/commits/main`.
Blob identities came from the pinned recursive Git trees. Commit/line links
for the conclusions are in `ROW-DEFINITION.md`. This is source-reviewed
provenance, not reproduced runtime evidence or an exhaustive web search.
