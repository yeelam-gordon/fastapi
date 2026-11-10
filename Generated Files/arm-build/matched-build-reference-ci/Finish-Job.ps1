$ErrorActionPreference = 'Stop'
$workspace = $env:GITHUB_WORKSPACE
$evidence = Join-Path $workspace 'matched-job-evidence'
$prep = Join-Path $workspace 'matched-evidence'
$case = Join-Path $workspace 'matched-case'
$windows = $env:MATCHED_ENTRY_MODE -ceq 'windows-self-identity'
$complete = ($windows -and $env:MATCHED_STAGE_OUTCOME -ceq 'success' -and
    $env:MATCHED_RUN_OUTCOME -ceq 'success') -or
    ($env:MATCHED_ENTRY_MODE -ceq 'mac-existing-controller' -and $env:MATCHED_JOB_STATUS -ceq 'success')
$notLaunched = $windows -and $env:MATCHED_STAGE_OUTCOME -ceq 'skipped' -and
    $env:MATCHED_RUN_OUTCOME -ceq 'skipped'
$safe = $complete -or ($notLaunched -and
    -not (Test-Path -LiteralPath $prep) -and -not (Test-Path -LiteralPath $case) -and
    -not (Test-Path -LiteralPath (Join-Path $evidence 'metadata-controller-stage.json')) -and
    -not (Test-Path -LiteralPath (Join-Path $evidence 'metadata-controller-run.json')))
# Legacy separate-probe artifacts never constitute completion evidence.
$probePending = (Test-Path -LiteralPath (Join-Path $workspace 'matched-controller-probe')) -or
    (Test-Path -LiteralPath (Join-Path $evidence 'controller.stderr')) -or
    (Test-Path -LiteralPath (Join-Path $evidence 'controller.json'))
if ($probePending) { $safe = $false }
if ($complete) {
    foreach ($path in @((Join-Path $prep 'creation-receipt.json'), (Join-Path $prep 'commands.json'),
        (Join-Path $case 'outer-command.json'), (Join-Path $case 'verification-command.json'))) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $safe = $false }
    }
    if ($windows) {
        foreach ($operation in @('stage', 'run')) {
            if (-not (Test-Path -LiteralPath (Join-Path $evidence "metadata-controller-$operation.json") -PathType Leaf)) {
                $safe = $false
            }
        }
    }
    if (@(Get-ChildItem -LiteralPath $prep -Filter '*.command.json' -ErrorAction SilentlyContinue).Count -ne 5) {
        $safe = $false
    }
}
function Test-EntryChildDrained($Receipt) {
    return $null -ne $Receipt -and $Receipt.ownership_established -ceq $true -and
        $Receipt.returncode -eq 0 -and $Receipt.timed_out -ceq $false -and
        $Receipt.cleanup_complete -ceq $true -and $Receipt.survivors -ceq $false -and
        $Receipt.errors -is [array] -and $Receipt.errors.Count -eq 0 -and
        $Receipt.liveness -is [array] -and $Receipt.liveness.Count -eq 0
}
if (Test-Path -LiteralPath $prep) {
    foreach ($command in Get-ChildItem -LiteralPath $prep -Filter '*.command.json') {
        $result = $command.FullName -replace '\.command\.json$', '.result.json'
        if (-not (Test-Path -LiteralPath $result)) { $safe = $false; continue }
        $receipt = (Get-Content -Raw -LiteralPath $result | ConvertFrom-Json).owned_receipt
        if (-not (Test-EntryChildDrained $receipt)) { $safe = $false }
    }
}
foreach ($pair in @(@('outer-command.json', 'outer-owned-receipt.json'), @('verification-command.json', 'verification-owned-receipt.json'))) {
    if (Test-Path -LiteralPath (Join-Path $case $pair[0])) {
        $path = Join-Path $case $pair[1]
        if (-not (Test-Path -LiteralPath $path)) { $safe = $false; continue }
        $receipt = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
        if (-not (Test-EntryChildDrained $receipt)) { $safe = $false }
    }
}
@{
    elapsed_seconds = ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - [long]$env:MATCHED_JOB_START_MS) / 1000
    excludes = 'queue, this publication, artifact upload, post-job cleanup'
    performance_claim = $false
    raw_collection_safe = $safe
    controller_entry_mode = $env:MATCHED_ENTRY_MODE
    stage_outcome = $env:MATCHED_STAGE_OUTCOME
    run_outcome = $env:MATCHED_RUN_OUTCOME
    entries_reported_skipped = $notLaunched
    explicit_not_launched = $notLaunched -and $safe
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'job-wall.json') -Encoding utf8
$publication = $evidence
if (-not $safe) {
    $publication = Join-Path $workspace 'matched-publication-evidence'
    New-Item -ItemType Directory -Path $publication -ErrorAction Stop | Out-Null
    Copy-Item -LiteralPath (Join-Path $evidence 'job-wall.json') -Destination (Join-Path $publication 'job-wall.json')
}
$seal = [ordered]@{}
$roots = if ($safe) {
    @('matched-job-evidence', 'matched-case', 'matched-evidence', 'matched-output', 'matched-verification')
} else { @('matched-publication-evidence') }
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
    Set-Content -LiteralPath (Join-Path $publication 'publication-seal.json') -Encoding utf8
'artifact-paths<<MATCHED_PATHS' >> $env:GITHUB_OUTPUT
$(if ($safe) { 'matched-job-evidence' } else { 'matched-publication-evidence' }) >> $env:GITHUB_OUTPUT
if ($safe) {
    @('matched-evidence', 'matched-case', 'matched-output', 'matched-verification',
      'matched-sdk', 'matched-venv', 'matched-wheels', 'package-source') >> $env:GITHUB_OUTPUT
}
'MATCHED_PATHS' >> $env:GITHUB_OUTPUT
