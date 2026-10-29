# CI is prepared but authorization prevented execution

The active GitHub OAuth token lacks `workflow` scope. GitHub rejected the authenticated push with:

```text
refusing to allow an OAuth App to create or update workflow
.github/workflows/arm-build-experiment.yml without workflow scope
```

No experiment workflow was created remotely, no runner was started, and no Windows/Mac parity result exists. The fork itself was created successfully; upstream permissions and workflows were not changed. The user was unavailable when authorization was requested, so no interactive authentication flow was started.

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

The resolver job creates identical universal dependency locks for both jobs. Download and preserve the `experiment-locks`, `arm-build-windows-11-arm`, `arm-build-macos-15` and `windows-arm-wheelhouse` artifacts under this experiment directory using `gh run download <run-id> --repo yeelam-gordon/fastapi --dir <explicit-directory>`.

Compare seven-trial medians and ranges from `report.json`, include bootstrap JSON durations separately, inspect artifact equivalence and installed-wheel smoke results, and retain actual runner image/core/interpreter-platform metadata. Repeat across independent jobs before asserting stable parity. Once a dependency set is accepted, freeze those returned lockfiles for subsequent cross-run comparisons rather than continually resolving newer versions.

This workflow is an opt-in measurement lane. Do not replace the existing release workflow, publish artifacts, or remove functional tests to obtain a better timing.
