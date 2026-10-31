$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$private = Join-Path $env:GITHUB_WORKSPACE 'p63-private-hosted'
$public = Join-Path $env:GITHUB_WORKSPACE 'p63-public'
$workspace = $env:GITHUB_WORKSPACE
$privateVerified = $false
$code = 2
try {
    New-Item -ItemType Directory -Path $public -ErrorAction Stop | Out-Null
    if (Test-Path -LiteralPath $private) { throw 'FRESH_PRIVATE_ROOT_REQUIRED' }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($identity.User)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($identity.User, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    [IO.FileSystemAclExtensions]::CreateDirectory($acl, $private) | Out-Null
    $item = Get-Item -LiteralPath $private -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'PRIVATE_ROOT_REPARSE' }
    $actual = Get-Acl -LiteralPath $private
    $rules = @($actual.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    $expectedSids = @($identity.User.Value, 'S-1-5-18') | Select-Object -Unique
    if (-not $actual.AreAccessRulesProtected -or
        $actual.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $identity.User.Value -or
        $rules.Count -ne $expectedSids.Count) { throw 'PRIVATE_ROOT_ACL' }
    foreach ($rule in $rules) {
        if ($rule.IsInherited -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl -or
            $rule.InheritanceFlags -ne ([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit) -or
            $rule.PropagationFlags -ne [Security.AccessControl.PropagationFlags]::None -or
            $rule.IdentityReference.Value -notin $expectedSids) { throw 'PRIVATE_ROOT_ACL' }
    }
    if (@($rules.IdentityReference.Value | Select-Object -Unique).Count -ne $expectedSids.Count) { throw 'PRIVATE_ROOT_ACL' }
    $privateVerified = $true
    & {
        $env:GITHUB_WORKSPACE = $private
        $env:GITHUB_ENV = Join-Path $private 'bootstrap-env.txt'
        foreach ($name in @('home', 'scratch')) {
            New-Item -ItemType Directory -Path (Join-Path $private $name) | Out-Null
        }
        $env:HOME = $env:USERPROFILE = $env:APPDATA = $env:LOCALAPPDATA = Join-Path $private 'home'
        $env:TEMP = $env:TMP = Join-Path $private 'scratch'
        $bootstrap = Join-Path $PSScriptRoot '..\paired-arm-reference\bootstrap.ps1'
        & $bootstrap
        if ($LASTEXITCODE) { throw 'PYTHON_BOOTSTRAP_FAILED' }
        $archive = Join-Path $private 'uv.zip'
        Invoke-WebRequest 'https://github.com/astral-sh/uv/releases/download/0.13.6/uv-aarch64-pc-windows-msvc.zip' -OutFile $archive
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'c2426c0c8e28b53d8c440e47a18d96ad4db51e159866c0e81435b196d7f0081c') {
            throw 'UV_ARCHIVE_HASH'
        }
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $private 'uv')
        $uv = Join-Path $private 'uv\uv.exe'
        if ((Get-FileHash -LiteralPath $uv -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'ec27977d62b5f6091bce410a8e69d40d07541803314e0120905c0ad0affaa5cc') {
            throw 'UV_EXECUTABLE_HASH'
        }
        $python = Join-Path $private 'paired-reference\python\python.exe'
        $env:GITHUB_WORKSPACE = $workspace
        Set-Location -LiteralPath $private
        & $python -I -B (Join-Path $PSScriptRoot 'hosted.py') --run $private $uv (Join-Path $public 'public-result.json')
        $script:code = $LASTEXITCODE
        if ($script:code -eq 0) { $script:code = 2 }
    } *> (Join-Path $private 'bootstrap-and-integration.log')
} catch {
    $failure = $_
    try {
        if ($privateVerified) {
            $failure | Out-String | Set-Content -LiteralPath (Join-Path $private 'bootstrap-error.txt') -Encoding UTF8
        }
    } catch {}
    $code = 2
}
try {
    if ((Test-Path -LiteralPath $public) -and -not (Test-Path -LiteralPath (Join-Path $public 'public-result.json'))) {
        '{"status":"UNKNOWN","diagnostic_ready":false,"category":"PRIVATE_BOOTSTRAP_FAILURE","stage":"BOOTSTRAP_UNKNOWN"}' |
            Set-Content -LiteralPath (Join-Path $public 'public-result.json') -Encoding UTF8
    }
    if ($privateVerified) {
        @{ exit_code = $code } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $private 'final-exit-code.json') -Encoding UTF8
    }
} catch { $code = 2 }
exit $code
