$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot ('test-publication-' + [guid]::NewGuid().ToString('N'))
$keys = @('GITHUB_WORKSPACE', 'GITHUB_OUTPUT', 'MATCHED_JOB_START_MS', 'MATCHED_ENTRY_MODE',
    'MATCHED_STAGE_OUTCOME', 'MATCHED_RUN_OUTCOME', 'MATCHED_JOB_STATUS')
$saved = @{}
foreach ($key in $keys) { $saved[$key] = [Environment]::GetEnvironmentVariable($key) }
try {
    foreach ($scenario in @('explicit-not-launched', 'not-launched-with-data', 'unknown-empty', 'early-failure',
        'stage-cancelled', 'run-failure', 'success-without-records', 'complete-success',
        'missing-receipt', 'timeout', 'unqualified-success', 'legacy-stream')) {
        $workspace = Join-Path $root $scenario
        $job = Join-Path $workspace 'matched-job-evidence'
        $null = New-Item -ItemType Directory -Path $job -Force
        $env:GITHUB_WORKSPACE = $workspace
        $env:GITHUB_OUTPUT = Join-Path $workspace 'outputs.txt'
        $env:MATCHED_JOB_START_MS = [string]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
        $env:MATCHED_ENTRY_MODE = 'windows-self-identity'
        $env:MATCHED_STAGE_OUTCOME = ''
        $env:MATCHED_RUN_OUTCOME = ''
        if ($scenario -cin @('explicit-not-launched', 'not-launched-with-data')) {
            $env:MATCHED_STAGE_OUTCOME = 'skipped'; $env:MATCHED_RUN_OUTCOME = 'skipped'
        } elseif ($scenario -ceq 'early-failure') {
            $env:MATCHED_STAGE_OUTCOME = 'failure'; $env:MATCHED_RUN_OUTCOME = 'skipped'
        } elseif ($scenario -ceq 'stage-cancelled') {
            $env:MATCHED_STAGE_OUTCOME = 'cancelled'; $env:MATCHED_RUN_OUTCOME = 'skipped'
        } elseif ($scenario -ceq 'run-failure') {
            $env:MATCHED_STAGE_OUTCOME = 'success'; $env:MATCHED_RUN_OUTCOME = 'failure'
        } elseif ($scenario -cin @('success-without-records', 'complete-success')) {
            $env:MATCHED_STAGE_OUTCOME = 'success'; $env:MATCHED_RUN_OUTCOME = 'success'
        }
        if ($scenario -ceq 'not-launched-with-data') {
            $null = New-Item -ItemType Directory -Path (Join-Path $workspace 'matched-evidence')
        }
        if ($scenario -ceq 'complete-success') {
            $prep = Join-Path $workspace 'matched-evidence'
            $case = Join-Path $workspace 'matched-case'
            $null = New-Item -ItemType Directory -Path $prep, $case
            '{}' | Set-Content -LiteralPath (Join-Path $prep 'creation-receipt.json')
            '[]' | Set-Content -LiteralPath (Join-Path $prep 'commands.json')
            $receipt = @{
                returncode = 0; timed_out = $false; ownership_established = $true
                cleanup_complete = $true; survivors = $false; errors = @(); liveness = @()
            }
            foreach ($label in @('install', 'find', 'venv', 'probe', 'backend')) {
                '{}' | Set-Content -LiteralPath (Join-Path $prep "$label.command.json")
                @{ owned_receipt = $receipt } | ConvertTo-Json -Depth 4 |
                    Set-Content -LiteralPath (Join-Path $prep "$label.result.json")
            }
            foreach ($label in @('outer', 'verification')) {
                '{}' | Set-Content -LiteralPath (Join-Path $case "$label-command.json")
                $receipt | ConvertTo-Json -Depth 3 |
                    Set-Content -LiteralPath (Join-Path $case "$label-owned-receipt.json")
            }
            foreach ($operation in @('stage', 'run')) {
                '{"scope":"SELF_IDENTITY_ONLY_NOT_OWNERSHIP_OR_MEASURED_SDK"}' |
                    Set-Content -LiteralPath (Join-Path $job "metadata-controller-$operation.json")
            }
        }
        $handle = $null
        if ($scenario -cin @('missing-receipt', 'timeout', 'unqualified-success', 'legacy-stream')) {
            $stream = Join-Path $job 'controller.stderr'
            [IO.File]::WriteAllText($stream, 'SIMULATED_LIVE_LEGACY_OUTPUT')
            $handle = [IO.File]::Open($stream, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
            if ($scenario -cne 'legacy-stream') {
                $probe = Join-Path $workspace 'matched-controller-probe'
                $null = New-Item -ItemType Directory -Path $probe
                '{}' | Set-Content -LiteralPath (Join-Path $probe 'command.json')
                if ($scenario -cne 'missing-receipt') {
                    @{ cleanup_complete = ($scenario -ceq 'unqualified-success'); timed_out = $true } |
                        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $probe 'owned-receipt.json')
                }
            }
        }
        try { & (Join-Path $PSScriptRoot 'Finish-Job.ps1') }
        finally { if ($handle) { $handle.Dispose() } }
        $wall = Get-Content -Raw -LiteralPath (Join-Path $job 'job-wall.json') | ConvertFrom-Json
        $paths = Get-Content -Raw -LiteralPath $env:GITHUB_OUTPUT
        if ($scenario -cin @('explicit-not-launched', 'complete-success')) {
            if ($wall.raw_collection_safe -cne $true -or $paths -notmatch 'matched-job-evidence') {
                throw "Proved entry state not retained: $scenario"
            }
        } else {
            if ($wall.raw_collection_safe -cne $false -or
                $paths -notmatch 'matched-publication-evidence' -or
                $paths -match 'matched-job-evidence|matched-controller-probe|matched-output') {
                throw "Unsafe artifact paths: $scenario"
            }
            $publication = Join-Path $workspace 'matched-publication-evidence'
            if (@(Get-ChildItem -LiteralPath $publication -File).Count -ne 2 -or
                (Get-Content -Raw -LiteralPath (Join-Path $publication 'publication-seal.json')) -match 'controller|stderr') {
                throw "Unsafe output sealed or copied: $scenario"
            }
        }
    }
    Write-Output 'PASS: explicit no-launch/complete states; unknown/early-failed/cancelled/incomplete entries unsafe without markers; locked legacy streams withheld; synthetic only'
} finally {
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key]) }
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
