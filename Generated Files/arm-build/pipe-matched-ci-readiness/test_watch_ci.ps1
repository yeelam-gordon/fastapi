$ErrorActionPreference = 'Stop'
$runId = 90000000001
$sha = '1' * 40
$statePath = Join-Path $PSScriptRoot "watch-state-$runId.json"
if (Test-Path -LiteralPath $statePath) { throw 'Refusing to overwrite an existing test-state path' }
if (Test-Path variable:global:NativeLinkWatchTest) { throw 'Refusing to replace existing test mocks' }
$global:NativeLinkWatchTest = @{
    caseNumber = 0
    statePaths = [System.Collections.Generic.List[string]]::new()
}

function gh {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'run') {
        if ($args[1] -ne 'cancel' -or $args[2] -ne $global:NativeLinkWatchTest.runId) { throw 'Unexpected cancellation target' }
        $global:NativeLinkWatchTest.cancellations++
        return
    }
    if ($args -contains '--include') {
        return "HTTP/2.0 200 OK`ndate: $($global:NativeLinkWatchTest.serverDate)`n`n$($global:NativeLinkWatchTest.run | ConvertTo-Json -Compress)"
    }
    return (@{ jobs = $global:NativeLinkWatchTest.jobs } | ConvertTo-Json -Depth 4 -Compress)
}

function Start-Sleep {
    param([int]$Seconds)
    if ($Seconds -ne 30) { throw 'Unexpected poll interval' }
    throw 'TEST_FIRST_POLL_COMPLETE'
}

function Test-WatchCase {
    param(
        [string]$Name,
        [string]$ServerDate,
        [object[]]$Jobs,
        [string]$ExpectedError,
        [int]$ExpectedCancellations,
        [bool]$WrongSource = $false,
        [bool]$WrongBranch = $false
    )
    $global:NativeLinkWatchTest.serverDate = $ServerDate
    $global:NativeLinkWatchTest.jobs = $Jobs
    $global:NativeLinkWatchTest.cancellations = 0
    $global:NativeLinkWatchTest.runId = $runId + $global:NativeLinkWatchTest.caseNumber
    $global:NativeLinkWatchTest.caseNumber++
    $casePath = Join-Path $PSScriptRoot "watch-state-$($global:NativeLinkWatchTest.runId).json"
    if (Test-Path -LiteralPath $casePath) { throw 'Refusing to overwrite an existing case-state path' }
    $global:NativeLinkWatchTest.statePaths.Add($casePath)
    $global:NativeLinkWatchTest.run = @{
        head_sha = $(if ($WrongSource) { '2' * 40 } else { $sha })
        run_attempt = 1
        workflow_id = 400482741
        event = 'workflow_dispatch'
        head_branch = $(if ($WrongBranch) { 'perf/native-link-build-20261104' } else { 'perf/worker-pipe-hobl-20261105' })
        repository = @{ full_name = 'yeelam-gordon/fastapi' }
        created_at = '2026-11-04T14:09:03Z'
        status = 'queued'
        conclusion = $null
    }
    $caught = $null
    try { & (Join-Path $PSScriptRoot 'watch_ci.ps1') -RunId $global:NativeLinkWatchTest.runId -ExpectedSha $sha }
    catch { $caught = $_.Exception.Message }
    if ($caught -ne $ExpectedError -or $global:NativeLinkWatchTest.cancellations -ne $ExpectedCancellations) {
        throw "$Name failed: error=$caught cancellations=$($global:NativeLinkWatchTest.cancellations)"
    }
    Write-Output "PASS: $Name"
}

try {
    $queued = @(@{ status = 'queued'; conclusion = $null })
    $poll = 'TEST_FIRST_POLL_COMPLETE'
    $bound = 'Admission job-count or queue bound exceeded; no rerun authorized'
    Test-WatchCase 'server age181 not local skew' 'Wed, 04 Nov 2026 14:12:04 GMT' $queued $poll 0
    Test-WatchCase 'exact300s boundary' 'Wed, 04 Nov 2026 14:14:03 GMT' $queued $poll 0
    Test-WatchCase 'real301s overrun' 'Wed, 04 Nov 2026 14:14:04 GMT' $queued $bound 1
    Test-WatchCase 'empty job list remains bounded' 'Wed, 04 Nov 2026 14:12:04 GMT' @() $poll 0
    Test-WatchCase 'queued run without jobs exceeds bound' 'Wed, 04 Nov 2026 14:14:04 GMT' @() $bound 1
    Test-WatchCase 'aggregate queued status cannot override running jobs' 'Wed, 04 Nov 2026 14:14:04 GMT' @(@{ status = 'in_progress'; conclusion = $null }) $poll 0
    Test-WatchCase 'wrong source never cancelled' 'Wed, 04 Nov 2026 14:14:04 GMT' $queued 'Run identity/source/attempt differs from admission; no cancellation justified' 0 $true
    Test-WatchCase 'old branch never cancelled' 'Wed, 04 Nov 2026 14:14:04 GMT' $queued 'Run identity/source/attempt differs from admission; no cancellation justified' 0 -WrongBranch $true
    Test-WatchCase 'contradictory clock never cancelled' 'Wed, 04 Nov 2026 14:08:03 GMT' $queued 'GitHub server date predates run creation; no cancellation justified' 0
}
finally {
    foreach ($casePath in $global:NativeLinkWatchTest.statePaths) {
        if (Test-Path -LiteralPath $casePath) { Remove-Item -LiteralPath $casePath }
    }
    Remove-Variable -Name NativeLinkWatchTest -Scope Global
}
