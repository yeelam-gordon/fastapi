[CmdletBinding()]
param([Parameter(Mandatory)][string]$ToolRoot)
$ErrorActionPreference = 'Stop'

function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$arm = Join-Path $ToolRoot 'Generated Files\arm-build'
$driver = Join-Path $arm 'hosted-devdrive-hobl-source-20261111'
$reference = Join-Path $arm 'pipe-matched-ci-readiness'
$manifestPath = Join-Path $driver 'SOURCEPINS.json'
$manifestSha = Get-Sha256 $manifestPath
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$workflow = Join-Path $ToolRoot '.github\workflows\arm-build-diagnostics.yml'
$review = Get-Content -Raw -LiteralPath (Join-Path $driver 'PARENT-REVIEW.json') | ConvertFrom-Json
$allocation = $review.ci_execution
if ($env:GITHUB_REPOSITORY -cne 'yeelam-gordon/fastapi' -or
    $env:GITHUB_RUN_ATTEMPT -cne '1' -or $env:MATCHED_JOB_SECONDS -cne '600' -or
    $env:MATCHED_PROFILE -cne 'stock-hobl-storage-ci82-v1' -or
    $review.approved -isnot [bool] -or -not $review.approved -or
    $review.cli_identity_qualified -isnot [bool] -or -not $review.cli_identity_qualified -or
    $review.profile -cne $env:MATCHED_PROFILE -or $review.sourcepins_sha256 -cne $manifestSha -or
    $allocation.question -cne 'hosted-stock-collection-boundaries' -or
    $env:HOBL_COLLECTION_BOUNDARY_DIAGNOSTIC -cne '1' -or
    (@($allocation.observation_schedule) -join ',') -cne 'OFF,ON,ON,OFF' -or
    $allocation.question_sha256 -cne (Get-Sha256 (Join-Path $PSScriptRoot 'COLLECTION-QUESTION.md')) -or
    $allocation.jobs -ne 2 -or $allocation.job_seconds -ne 600 -or $allocation.hobl_rows -cne 'AAAA' -or
    $allocation.workflow_sha256 -cne (Get-Sha256 $workflow) -or
    $allocation.cli_provenance_sha256 -cne (Get-Sha256 (Join-Path $PSScriptRoot 'CLI-PROVENANCE.md')) -or
    $allocation.verifier_sha256 -cne (Get-Sha256 (Join-Path $PSScriptRoot 'verify_stock_reference.py')) -or
    $allocation.diagnostic_verifier_sha256 -cne (Get-Sha256 (Join-Path $PSScriptRoot 'verify_collection_boundaries.py')) -or
    $allocation.gate_sha256 -cne (Get-Sha256 $PSCommandPath)) {
    throw 'NoParityClaim: exact two-job stock source/allocation review required'
}

foreach ($group in 'successor', 'reference') {
    $base = if ($group -eq 'successor') { $driver } else { $arm }
    foreach ($pin in $manifest.$group.PSObject.Properties) {
        if ((Get-Sha256 (Join-Path $base $pin.Name)) -cne $pin.Value) {
            throw "NoParityClaim: source closure changed: $($pin.Name)"
        }
    }
}
foreach ($name in 'queue_readiness.ps1', 'required-backend-ci-readiness/queue_clock.ps1') {
    if ((Get-Sha256 (Join-Path $reference $name)) -cne $allocation.queue_sha256.$name) {
        throw "NoParityClaim: queue guard changed: $name"
    }
}
Write-Output "Reviewed stock reference source closure: $manifestSha"
