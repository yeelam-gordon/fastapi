[CmdletBinding()]
param([switch]$SourceOnly)
$ErrorActionPreference = 'Stop'
$root = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).FullName
$manifestPath = Join-Path $PSScriptRoot 'RELEASE.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$core = Join-Path $PSScriptRoot '..\matched-build-reference-screen'
$pin = (Get-FileHash -LiteralPath (Join-Path $core 'SOURCEPINS.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($pin -cne '29c9e239434dfcf1479c2767de26d6df1088e9bcd85a3989241af993540b86e6' -or
    $manifest.core_sourcepins_sha256 -cne $pin) { throw 'Qualified core pin differs' }
$pins = Get-Content -Raw -LiteralPath (Join-Path $core 'SOURCEPINS.json') | ConvertFrom-Json
$expected = @($pins.files.PSObject.Properties.Name) + 'SOURCEPINS.json'
$actual = @(Get-ChildItem -LiteralPath $core -Force -File | Select-Object -ExpandProperty Name)
if (@(Compare-Object $expected $actual).Count -ne 0 -or
    @(Get-ChildItem -LiteralPath $core -Force -Directory).Count -ne 0) {
    throw 'Core deployment must contain only the 30 pinned files plus SOURCEPINS'
}
foreach ($entry in $pins.files.PSObject.Properties) {
    $path = Join-Path $core $entry.Name
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {
        throw "Core byte mismatch: $($entry.Name)"
    }
}
foreach ($entry in $manifest.files.PSObject.Properties) {
    if ($entry.Name -match '(^[\\/]|(^|[\\/])\.\.([\\/]|$)|:)') { throw 'Unsafe release path' }
    $relative = $entry.Name.Replace([char]92, [IO.Path]::DirectorySeparatorChar).Replace([char]47, [IO.Path]::DirectorySeparatorChar)
    $path = Join-Path $root $relative
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {
        throw "Combined source hash mismatch: $($entry.Name)"
    }
}
if ($SourceOnly) {
    Write-Output "SOURCE_BYTES_VERIFIED; NOTADMITTED; $pin"
    return
}
$selection = [Environment]::GetEnvironmentVariable('MATCHED_REFERENCE_HOST')
if ($null -eq $selection) { $selection = 'both' }
if ($selection -cnotin @('both', 'windows', 'darwin')) { throw 'Invalid reference-host selection' }
$jobs = if ($selection -ceq 'both') { 2 } else { 1 }
if ($env:GITHUB_REPOSITORY -cne 'yeelam-gordon/fastapi' -or $env:GITHUB_RUN_ATTEMPT -cne '1' -or
    $env:GITHUB_EVENT_NAME -cne 'workflow_dispatch' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:RUNNER_ARCH -cne 'ARM64') { throw 'Exact manual fork native hosted context required' }
$review = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'PARENT-REVIEW.json') | ConvertFrom-Json
if ($review.approved -cne $true -or
    ($review.maximum_jobs -isnot [int] -and $review.maximum_jobs -isnot [long]) -or
    $review.maximum_jobs -ne $jobs) {
    throw 'NOTADMITTED: zero approved jobs'
}
$reviewHost = if ($null -eq $review.PSObject.Properties['reference_host']) { 'both' } else { $review.reference_host }
if ($reviewHost -cne $selection -or
    ($selection -ceq 'windows' -and $env:RUNNER_OS -cne 'Windows') -or
    ($selection -ceq 'darwin' -and $env:RUNNER_OS -cne 'macOS')) {
    throw 'reference-host/platform/parent job ceiling mismatch'
}
if ($manifest.hosted_raw_verifier_ready -cne $true) { throw 'Portable verifier source not ready' }
if ($env:RUNNER_OS -ceq 'Windows' -and
    $manifest.windows_controller_mode -cne 'self-identity-existing-entry-unowned-startup') {
    throw 'Explicit Windows controller startup boundary required'
}
$now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000
if ($review.delegated_native_admission -cne $true -or
    ($review.expected_run_number -isnot [long] -and $review.expected_run_number -isnot [int]) -or
    [string]$review.expected_run_number -cne $env:GITHUB_RUN_NUMBER -or
    -not [double]::IsFinite([double]$review.issued_unix) -or
    -not [double]::IsFinite([double]$review.expires_unix) -or
    $review.issued_unix -gt $now -or $review.expires_unix -le $now -or
    $review.expires_unix - $review.issued_unix -le 0 -or
    $review.expires_unix - $review.issued_unix -gt 1800) { throw 'Separate finite one-run parent delegation required' }
Write-Output 'SOURCE_READY_NATIVE_UNKNOWN; separate finite parent allocation checked'
