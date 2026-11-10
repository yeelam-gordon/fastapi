$ErrorActionPreference = 'Stop'
$workspace = $env:GITHUB_WORKSPACE
$evidence = Join-Path $workspace 'matched-job-evidence'
$safe = $true
$prep = Join-Path $workspace 'matched-evidence'
if (Test-Path -LiteralPath $prep) {
    foreach ($command in Get-ChildItem -LiteralPath $prep -Filter '*.command.json') {
        $result = $command.FullName -replace '\.command\.json$', '.result.json'
        if (-not (Test-Path -LiteralPath $result)) { $safe = $false; continue }
        $receipt = (Get-Content -Raw -LiteralPath $result | ConvertFrom-Json).owned_receipt
        if ($receipt.cleanup_complete -cne $true -or $receipt.survivors -cne $false) { $safe = $false }
    }
}
$case = Join-Path $workspace 'matched-case'
foreach ($pair in @(@('outer-command.json', 'outer-owned-receipt.json'), @('verification-command.json', 'verification-owned-receipt.json'))) {
    if (Test-Path -LiteralPath (Join-Path $case $pair[0])) {
        $path = Join-Path $case $pair[1]
        if (-not (Test-Path -LiteralPath $path)) { $safe = $false; continue }
        $receipt = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
        if ($receipt.cleanup_complete -cne $true -or $receipt.survivors -cne $false) { $safe = $false }
    }
}
@{
    elapsed_seconds = ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - [long]$env:MATCHED_JOB_START_MS) / 1000
    excludes = 'queue, this publication, artifact upload, post-job cleanup'
    performance_claim = $false
    raw_collection_safe = $safe
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'job-wall.json') -Encoding utf8
$seal = [ordered]@{}
$roots = @('matched-job-evidence')
if ($safe) { $roots += @('matched-case', 'matched-evidence', 'matched-output', 'matched-verification') }
foreach ($name in $roots) {
    $root = Join-Path $workspace $name
    if (-not (Test-Path -LiteralPath $root)) { continue }
    foreach ($file in Get-ChildItem -LiteralPath $root -File -Recurse -Force) {
        if ($file.Name -ceq 'publication-seal.json') { continue }
        $seal[[IO.Path]::GetRelativePath($workspace, $file.FullName)] =
            (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$seal | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $evidence 'publication-seal.json') -Encoding utf8
'artifact-paths<<MATCHED_PATHS' >> $env:GITHUB_OUTPUT
'matched-job-evidence' >> $env:GITHUB_OUTPUT
if ($safe) {
    @('matched-evidence', 'matched-case', 'matched-output', 'matched-verification',
      'matched-sdk', 'matched-venv', 'matched-wheels', 'package-source') >> $env:GITHUB_OUTPUT
}
'MATCHED_PATHS' >> $env:GITHUB_OUTPUT
