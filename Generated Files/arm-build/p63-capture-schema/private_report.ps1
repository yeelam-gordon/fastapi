param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][ValidateSet('Preflight','Decode')][string]$Phase
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    if ($Phase -eq 'Preflight') {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'ADMIN_TOKEN_REQUIRED'
        }
        $acl = [Security.AccessControl.DirectorySecurity]::new()
        $acl.SetOwner($identity.User)
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($sid in @($identity.User, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
            $rule = [Security.AccessControl.FileSystemAccessRule]::new(
                $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
            $acl.AddAccessRule($rule)
        }
        Set-Acl -LiteralPath $Root -AclObject $acl
        $command = Get-Command Get-MpPerformanceReport -ErrorAction Stop
        $source = Join-Path $command.Module.ModuleBase 'MSFT_MpPerformanceRecording.psm1'
        $platform = (Get-ItemProperty -LiteralPath 'HKLM:\Software\Microsoft\Windows Defender' -Name InstallLocation).InstallLocation
        $decoder = Join-Path $platform 'MpCmdRun.exe'
        $wpr = Join-Path $env:SYSTEMROOT 'System32\wpr.exe'
        foreach ($tool in @($wpr, $decoder)) {
            if ((Get-AuthenticodeSignature -LiteralPath $tool).Status -ne 'Valid') { throw 'TOOL_SIGNATURE' }
            $stream = [IO.File]::OpenRead($tool)
            try {
                $reader = [IO.BinaryReader]::new($stream)
                $stream.Position = 60
                $offset = $reader.ReadInt32()
                $stream.Position = $offset
                if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0xaa64) { throw 'NATIVE_TOOL_REQUIRED' }
            } finally { $stream.Dispose() }
        }
        @{
            admin = $true
            native_arm = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() -eq 'Arm64' -and
                         [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString() -eq 'Arm64'
            module_version = $command.Module.Version.ToString()
            module_sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
            wpr_version = (Get-Item -LiteralPath $wpr).VersionInfo.FileVersion
            decoder_version = (Get-Item -LiteralPath $decoder).VersionInfo.FileVersion
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Root 'preflight.json') -Encoding UTF8
    } else {
        $script:report = $null
        $global:LASTEXITCODE = 0
        & {
            $script:report = Get-MpPerformanceReport -Path (Join-Path $Root 'raw.etl') -Raw -Overview -TopScans 4096 -ErrorAction Stop
        } *> (Join-Path $Root 'decoder-all-streams.log')
        if ($LASTEXITCODE -ne 0 -or $null -eq $script:report -or $null -eq $script:report.TopScans) {
            throw 'DECODER_FAILED'
        }
        foreach ($scan in $script:report.TopScans) {
            if ($scan.StartTime -isnot [uint64] -or $scan.EndTime -isnot [uint64] -or $scan.Duration -isnot [uint64]) {
                throw 'RAW_TIME_TYPE'
            }
            if ($null -ne $scan.ProcessId -and $scan.ProcessId -isnot [int]) { throw 'RAW_PID_TYPE' }
        }
        $script:report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $Root 'raw-report.json') -Encoding UTF8
    }
    exit 0
} catch {
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $Root 'private-powershell-error.txt') -Encoding UTF8
    exit 2
}
