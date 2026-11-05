param(
    [Parameter(Mandatory)][ValidateRange(1, [long]::MaxValue)][long]$RunId,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedSha
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'required-backend-ci-readiness\queue_clock.ps1')
$repo = 'yeelam-gordon/fastapi'
for ($poll = 1; $poll -le 32; $poll++) {
    $raw = gh api --include "repos/$repo/actions/runs/$RunId"
    if ($LASTEXITCODE -ne 0) { throw 'Run metadata fetch failed' }
    $parts = [regex]::Split(($raw -join "`n"), "\r?\n\r?\n", 2)
    if ($parts.Count -ne 2) { throw 'Missing response-header/body boundary; no cancellation justified' }
    $date = [regex]::Match($parts[0], '(?im)^date:\s*(.+)$')
    if (-not $date.Success) { throw 'Missing GitHub clock; no cancellation justified' }
    $serverDate = $date.Groups[1].Value.Trim()
    $run = $parts[1] | ConvertFrom-Json
    if ($run.head_sha -ne $ExpectedSha -or $run.run_attempt -ne 1 -or
        $run.workflow_id -ne 400482741 -or $run.event -ne 'workflow_dispatch' -or
        $run.head_branch -ne 'perf/worker-pipe-hobl-20261105' -or
        $run.repository.full_name -ne $repo) {
        throw 'Run identity/source/attempt differs from admission; no cancellation justified'
    }
    $raw = gh api "repos/$repo/actions/runs/$RunId/jobs?per_page=100"
    if ($LASTEXITCODE -ne 0) { throw 'Job metadata fetch failed' }
    $jobs = @((($raw | ConvertFrom-Json).jobs) | Where-Object { $_.conclusion -ne 'skipped' })
    $created = $run.created_at
    if ($created -is [DateTime]) {
        $created = ([DateTimeOffset]$created.ToUniversalTime()).ToString('o', [Globalization.CultureInfo]::InvariantCulture)
    }
    $age = Get-GitHubQueueAgeSeconds -CreatedAt $created -ServerDate $serverDate
    $state = @{
        run_id = $RunId
        source_sha = $run.head_sha
        poll = $poll
        age_seconds = $age
        age_clock = 'GitHub HTTP Date minus GitHub created_at; local wall clock unused'
        server_date = $serverDate
        status = $run.status
        conclusion = $run.conclusion
        jobs = @($jobs | Select-Object id,name,status,conclusion,started_at,completed_at,runner_name)
    }
    $state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $PSScriptRoot "watch-state-$RunId.json") -Encoding utf8NoBOM
    if ($run.status -eq 'completed') {
        $state | ConvertTo-Json -Depth 6
        if ($jobs.Count -gt 2) { throw 'Completed run exceeded admitted job count' }
        if ($run.conclusion -ne 'success') { exit 1 }
        exit 0
    }
    $statuses = if ($jobs.Count) { @($jobs | ForEach-Object { $_.status }) } else { @($run.status) }
    if ($jobs.Count -gt 2 -or (Test-GitHubQueueBound -AgeSeconds $age -JobStatuses $statuses)) {
        gh run cancel $RunId --repo $repo
        if ($LASTEXITCODE -ne 0) { throw 'Exact-run bounds cancellation failed' }
        throw 'Admission job-count or queue bound exceeded; no rerun authorized'
    }
    Start-Sleep -Seconds 30
}
throw 'Finite metadata watch exhausted; inspect this exact run, do not redispatch'
