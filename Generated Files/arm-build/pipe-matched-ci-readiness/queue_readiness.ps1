$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'required-backend-ci-readiness/queue_clock.ps1')
if ($env:GITHUB_REPOSITORY -ne 'yeelam-gordon/fastapi' -or $env:GITHUB_RUN_ATTEMPT -ne '1') {
    throw 'Owned fork attempt one required'
}
$raw = gh api --include "repos/$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID"
if ($LASTEXITCODE) { throw 'Server-clock metadata unavailable' }
$parts = [regex]::Split(($raw -join "`n"), "\r?\n\r?\n", 2)
if ($parts.Count -ne 2) { throw 'Missing server response boundary' }
$date = [regex]::Match($parts[0], '(?im)^date:\s*(.+)$')
if (-not $date.Success) { throw 'Missing server UTC clock' }
$run = $parts[1] | ConvertFrom-Json
if ($run.head_sha -ne $env:GITHUB_SHA -or $run.run_attempt -ne 1 -or $run.event -ne 'workflow_dispatch') {
    throw 'Unexpected run/source/attempt'
}
# PowerShell may decode ISO timestamps as DateTime: never reparse their local string form.
$created = $run.created_at
if ($created -is [DateTime]) {
    $created = ([DateTimeOffset]$created.ToUniversalTime()).ToString('o', [Globalization.CultureInfo]::InvariantCulture)
}
$age = Get-GitHubQueueAgeSeconds -CreatedAt $created -ServerDate $date.Groups[1].Value.Trim()
$rawJobs = gh api "repos/$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID/jobs?per_page=100"
if ($LASTEXITCODE) { throw 'Actual job state unavailable' }
$jobs = @((($rawJobs | ConvertFrom-Json).jobs) | Where-Object { $_.conclusion -ne 'skipped' })
$statuses = if ($jobs.Count) { @($jobs | ForEach-Object { $_.status }) } else { @($run.status) }
if ($jobs.Count -gt 2 -or (Test-GitHubQueueBound -AgeSeconds $age -JobStatuses $statuses)) {
    throw 'Finite job-count/actual queued-state bound exceeded; no cancellation or retry here'
}
Write-Output "PASS source-bound server-UTC queue admission: age=$age; actual jobs=$($jobs.Count)"
