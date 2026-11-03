param([Parameter(Mandatory)][string] $Private, [Parameter(Mandatory)][string] $Public)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $Public -ErrorAction Stop | Out-Null
$result = @{schema=1;stage='preflight';tool='controller';native_code=0;status='FAILED';reason='host_context';residual_buffers_possible=$false}
try {
    if ($env:GITHUB_ACTIONS -ne 'true' -or $env:GITHUB_REPOSITORY -ne 'yeelam-gordon/fastapi' -or
        $env:GITHUB_RUN_ATTEMPT -ne '1' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or
        $env:RUNNER_OS -ne 'Windows' -or $env:RUNNER_ARCH -ne 'ARM64' -or
        $env:GITHUB_REF -ne 'refs/heads/perf/hobl-build-etw-20261103') { throw 'host gate' }
    $result.reason = 'token'
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'token gate' }
    $result.reason = 'disk'
    if (([IO.DriveInfo]::new([IO.Path]::GetPathRoot($Private))).AvailableFreeSpace -lt 8GB) { throw 'disk gate' }
    $result.reason = 'tools'
    foreach ($tool in @('wpr.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $env:SystemRoot "System32\$tool") -PathType Leaf)) { throw 'tool gate' }
    }
    $result.reason = 'missing_dotnet10'
    if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw 'dotnet gate' }
    $result.reason = 'run_identity'
    $headers = @{Authorization="Bearer $env:GH_TOKEN";Accept='application/vnd.github+json'}
    $uri = "https://api.github.com/repos/yeelam-gordon/fastapi/actions/runs/$env:GITHUB_RUN_ID"
    $run = Invoke-RestMethod -Uri $uri -Headers $headers -TimeoutSec 15
    if ($run.workflow_id -ne 400482741 -or $run.head_sha -ne $env:GITHUB_SHA -or
        $run.head_branch -ne 'perf/hobl-build-etw-20261103' -or $run.run_attempt -ne 1 -or
        $run.event -ne 'workflow_dispatch') { throw 'run gate' }
    $result.reason = 'job_identity'
    $jobs = Invoke-RestMethod -Uri "$uri/jobs?per_page=100" -Headers $headers -TimeoutSec 15
    $active = @($jobs.jobs | Where-Object { $_.status -ne 'completed' -or $_.conclusion -ne 'skipped' })
    if ($jobs.total_count -gt 100 -or $active.Count -ne 1 -or $active[0].status -ne 'in_progress' -or
        $active[0].name -ne 'build-etw / trace' -or $active[0].runner_name -ne $env:RUNNER_NAME -or
        $active[0].labels -notcontains 'windows-11-arm' -or $active[0].labels -contains 'self-hosted') { throw 'job gate' }
    $result.reason = 'existing_recording'
    $result.tool = 'wpr'
    & (Join-Path $env:SystemRoot 'System32\wpr.exe') -status *> (Join-Path $Private 'preflight-status.log')
    $result.native_code = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0 -or (Get-Content (Join-Path $Private 'preflight-status.log') -Raw) -notmatch 'WPR is not recording') {
        throw 'recording gate'
    }
    $result.tool = 'logman'
    & (Join-Path $env:SystemRoot 'System32\logman.exe') query -ets *> (Join-Path $Private 'preflight-sessions.log')
    $result.native_code = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0 -or (Get-Content (Join-Path $Private 'preflight-sessions.log') -Raw) -match 'WPR_|BuildAttributionSystem|hobl-|NT Kernel Logger') {
        throw 'existing session gate'
    }
    $result.status = 'PASS'
    $result.reason = 'none'
} catch {
    $_ | Out-File -LiteralPath (Join-Path $Private 'preflight-error.log')
    if ($result.native_code -eq 0) { $result.native_code = -1 }
} finally {
    $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Public 'stage.json')
}
if ($result.status -ne 'PASS') { exit 1 }
