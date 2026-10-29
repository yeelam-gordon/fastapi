# CI execution and authorization

The user completed GitHub authorization, and both jobs of corrected run [40814588064](https://github.com/yeelam-gordon/fastapi/actions/runs/40814588064) passed. Two runs were dispatched in total. Strict cross-platform postprocessing rejected source-content and executable-mode differences, so no parity claim is accepted and no third run is scheduled.

The initial GitHub OAuth token lacked `workflow` scope. GitHub rejected the first authenticated push with:

```text
refusing to allow an OAuth App to create or update workflow
.github/workflows/arm-build-experiment.yml without workflow scope
```

That rejected attempt created no remote workflow or runner. The user subsequently completed authorization after a dialog request; redundant agent-started authentication/dialog helpers were stopped. Upstream permissions and workflows were not changed.

## Authorize and run

These commands require the user's GitHub authorization, not a token committed to a file:

```powershell
gh auth refresh --hostname github.com --scopes workflow
if ($LASTEXITCODE -ne 0) { throw 'Workflow authorization failed' }
git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push https://github.com/yeelam-gordon/fastapi.git HEAD:refs/heads/perf/windows-arm-build-experiment
if ($LASTEXITCODE -ne 0) { throw 'Fork push failed' }
gh repo edit yeelam-gordon/fastapi --default-branch perf/windows-arm-build-experiment
gh workflow run arm-build-experiment.yml --repo yeelam-gordon/fastapi --ref perf/windows-arm-build-experiment
gh run list --repo yeelam-gordon/fastapi --workflow arm-build-experiment.yml --limit 3
```

GitHub requires a manually dispatchable workflow to exist on the default branch. The default-branch change applies only to the newly created experimental fork, not upstream.

## Evidence to collect

The first run's resolver generated universal dependency locks; those exact outputs were frozen in the corrected run's commit. Download and preserve `experiment-locks`, `arm-build-windows-11-arm`, `arm-build-macos-15` and `windows-arm-wheelhouse` under this experiment directory using `gh run download <run-id> --repo yeelam-gordon/fastapi --dir <explicit-directory>`.

Compare seven-trial medians and ranges from `report.json`, include bootstrap JSON durations separately, inspect artifact equivalence and installed-wheel smoke results, and retain actual runner image/core/interpreter-platform metadata. Repeat across independent jobs before asserting stable parity. Once a dependency set is accepted, freeze those returned lockfiles for subsequent cross-run comparisons rather than continually resolving newer versions.

This workflow is an opt-in measurement lane. Do not replace the existing release workflow, publish artifacts, or remove functional tests to obtain a better timing.

## CI budget gate

The authoritative limited-capacity rule is in [CIRCUMSTANCES.md](../CIRCUMSTANCES.md#limited-fork-ci-capacity). This section records its application to actual dispatches.

The initial run `40814042898` completed: Windows ARM passed package measurements and installed-wheel smoke; macOS failed before provisioning because its valid native Python uses a `universal2` build tag. The corrected architecture guard is covered by local ARM-versus-Rosetta regression cases. Windows interpreter setup also consumed several minutes; the replacement managed-Python path installed native 3.13.15 locally in 6.24 seconds and passed a separate setup/build smoke check. These are the concrete reasons for the corrected second experiment, not an unrestricted rerun policy.

Corrected run: [40814588064](https://github.com/yeelam-gordon/fastapi/actions/runs/40814588064), commit `264cbad400c8336057a70b9b6a65bfdb4920321e`. Dispatch checks: 12 benchmark tests, 11 comparison tests, Ruff, actionlint, Node syntax, and the managed-Python setup plus complete PDM build on this Windows ARM host. Actual macOS execution and the runner download path remained runner-only checks. No third dispatch is planned without reviewing this result.

## Completed results and strict comparison disposition

Both corrected ARM jobs passed complete builds, per-platform artifact checks and installed-wheel smoke. Observed medians were Windows 3.129 s isolated / 2.679 s pre-provisioned, versus Mac 0.950 s / 0.730 s. The Windows-only wheelhouse export is experimental recovery overhead, not part of package-build timing.

The initial postprocessor rejected different harness hashes; the saved scripts differed only by CRLF/LF. Its correction verifies each raw hash, normalizes CRLF only for harness identity, and records the normalized identity. The corrected postprocessor then properly rejected **58 wheel-content, 1,080 sdist-content and five executable-mode differences**. [Rejected comparison receipt](results/ci-40814588064/comparison-r2.json). A green workflow is not an accepted artifact-identical comparison.

Local analysis traced content differences to `git archive` applying `core.autocrlf`. The harness now disables that conversion and records a canonical source manifest. A local five-pair rerun at the same package-source commit matches all Mac reference member contents; five script executable modes still differ. [Local diagnostics](results/environment/canonical-artifact-diagnostics.json). No differences were silently waived and no third CI run was used.

Later dispatch commands above are reproduction instructions, not a scheduled retry. Resolve the remaining artifact-acceptance question and meet the local-readiness gate before using them again.
