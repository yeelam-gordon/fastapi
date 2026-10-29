# FastAPI dashboard row: definition boundary

Source-only audit, 2026-10-29. **High confidence in the public export contract;
low confidence identifying the unattributed screenshot.** No matching renderer
was established. A project hyperlink, two OS durations and a percentage do not
identify the timer, aggregation, comparison denominator or revision.

## Confirmed public path, not a confirmed screenshot mapping

At HOBL branch commit `5e9e1ae540a8099485e30e2044ceb68d29d982e6`:

1. Windows writes `fast_api_results.csv`, containing `scenario_runtime`,
   `build_time`, `uv_build_time`, `test_time` and architecture; the aggregate is
   the sum of the three phase durations in seconds.
   [filename](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/scenarios/windows/fast_api/fast_api_resources/fast_api_run.ps1#L83),
   [sum and export](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/scenarios/windows/fast_api/fast_api_resources/fast_api_run.ps1#L417-L440).
   [Mac emits the same timing keys](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/scenarios/macos/mac_fast_api/mac_fast_api_resources/mac_fast_api_run.sh#L88-L107).
2. The generic JSON rollup reads CSV key/value pairs, converts numeric values
   and retains all ordinary metrics under `Metrics`; it does **not** select one
   FastAPI elapsed-time column.
   [CSV parsing](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/utilities/open_source/rollup_metrics_json.py#L130-L190),
   [run identity and Metrics](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/utilities/open_source/rollup_metrics_json.py#L249-L300).
3. Study JSON preserves run objects in `Runs`, using `Test Name` for scenario
   identity. Thus `Runs[*].Metrics.scenario_runtime` is an available field,
   **not proof that it becomes the displayed project row**.
   [identity](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/utilities/open_source/gen_study_report_json.py#L193-L207),
   [append](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/utilities/open_source/gen_study_report_json.py#L235-L243),
   [final schema](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/utilities/open_source/gen_study_report_json.py#L510-L527).
4. The exporter accepts `dashboard_url` and constructs a `result/Results?path=`
   link. That is a report-location link, not a FastAPI project hyperlink or
   cross-OS comparison renderer.
   [URL handling](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/utilities/open_source/gen_study_report_json.py#L34-L48),
   [Study URL](https://github.com/crutkas/HOBL/blob/5e9e1ae540a8099485e30e2044ceb68d29d982e6/utilities/open_source/gen_study_report_json.py#L510-L524).

The inspected public tree/report generators did not establish the screenshot's
row selector, elapsed formatting, percentage formula, OS pairing or across-run
aggregation. A separately hosted UI remains possible; its implementation and
revision are **unavailable in this evidence**, not proven nonexistent.

## Revision compatibility

Upstream main pinned to `df120528374c0a5de5cb5a526175973d1ea2b53f`
still exports `scenario_runtime = build_time + test_time`, without uv build.
[Actual old-contract export](https://github.com/microsoft/HOBL/blob/df120528374c0a5de5cb5a526175973d1ea2b53f/scenarios/windows/fast_api/fast_api_resources/fast_api_run.ps1#L387-L404).
Fork main `25801a08d0749bdac122fab688fd28a0faadbba9` has the same
Windows run-script blob as that upstream pin. Both JSON exporter blobs are
identical across these main pins and the audited feature branch (see provenance).
Consequently, a stable field name/export schema does not make old and new totals
semantically comparable. Neither main nor feature-branch semantics identify the
screenshot without its source revision.

## Existing workflow coverage, without retargeting

| Possible selected field/contract | Relevant existing coverage | Still insufficient |
|---|---|---|
| `build_time`: isolated `python -m build` | Package experiment and analysis-only build diagnostics overlap package/frontend costs | Not a reproduction of HOBL's pinned input/environment or dashboard |
| `uv_build_time`: separate stock `uv build` | Published manual diagnostic lane overlaps this package operation | Held, not run; no dashboard identity or matched HOBL reproduction |
| `test_time`: coverage pytest | Neither package lane measures the full upstream test phase | Installed-wheel smoke/collector tests are not this workload |
| `scenario_runtime`: old two-phase or new three-phase sum | Package work covers components only | Missing matching tests, versioned sum contract and report aggregation |
| Application startup/import/tests aggregate, or setup/reload | Existing package lanes do not cover these workloads | Distinct application harness, not interchangeable with maintainer metrics |
| Checkout/job wall time | Git-context diagnostics can describe preparation | Credential setup/cleanup intervals are not package-build or application-auth timers |

Prior command-boundary findings remain credited to
`arm-build\prior-work\hobl\AUDIT.md`; they are not new discoveries here.
Package creation can take seconds without explaining an aggregate row.

**Next scope gate:** obtain the public dashboard/report URL (including the
FastAPI hyperlink target), or the row's exact exported field/selector plus
producer/renderer revisions and aggregation/percentage definition. A value-free
schema or renderer source suffices; no private measurements or image upload are
needed. Until that mapping is established, retain build-first scope and the
current CI hold. No optimization proposal or workflow retargeting follows.
