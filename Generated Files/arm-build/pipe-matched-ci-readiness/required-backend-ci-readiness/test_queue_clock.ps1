$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'queue_clock.ps1')
$created = '2026-11-04T14:09:03Z'
$age = Get-GitHubQueueAgeSeconds -CreatedAt $created -ServerDate 'Wed, 04 Nov 2026 14:12:04 GMT'
if ($age -ne 181) { throw 'Server-clock age must be181, not local eight-hour-skew age' }
$decoded = '{"created_at":"2026-11-04T14:09:03Z"}' | ConvertFrom-Json
$decodedAge = Get-GitHubQueueAgeSeconds -CreatedAt $decoded.created_at -ServerDate 'Wed, 04 Nov 2026 14:12:04 GMT'
if ($decodedAge -ne 181) { throw 'Automatically decoded UTC DateTime must not be reinterpreted in local timezone' }
if (Test-GitHubQueueBound -AgeSeconds $age -JobStatuses @('queued','in_progress')) {
    throw 'The actual canceled run did not exceed its queue bound'
}
if (Test-GitHubQueueBound -AgeSeconds 300 -JobStatuses @('queued')) {
    throw 'The exact boundary does not yet exceed300 seconds'
}
if (-not (Test-GitHubQueueBound -AgeSeconds 301 -JobStatuses @('queued'))) {
    throw 'Real queue overrun must be recognized'
}
if (Test-GitHubQueueBound -AgeSeconds 900 -JobStatuses @('completed','in_progress')) {
    throw 'Elapsed time alone cannot fabricate a queued job'
}
$rejected = $false
try {
    Get-GitHubQueueAgeSeconds -CreatedAt $created -ServerDate 'not a server date' | Out-Null
}
catch { $rejected = $true }
if (-not $rejected) { throw 'Malformed server clock must reject before cancellation' }
$rejected = $false
try {
    Get-GitHubQueueAgeSeconds -CreatedAt $created -ServerDate 'Wed, 04 Nov 2026 14:08:03 GMT' | Out-Null
}
catch { $rejected = $true }
if (-not $rejected) { throw 'Contradictory server clock must reject before cancellation' }
Write-Output 'PASS: server-clock/skew regression, exact bound, real overrun, nonqueued state, malformed and contradictory clock.'
