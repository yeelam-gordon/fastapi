Set-StrictMode -Version Latest

function Get-SafeProperty($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -ne $property) { return $property.Value }
    return $null
}

function Get-VolumeKey($Value) {
    if ([string]$Value -match '^\\\\\?\\Volume\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}\\$') {
        return ([string]$Value).ToUpperInvariant()
    }
    return $null
}

function Get-SafeFileSystem($Value) {
    switch ([string]$Value) {
        'NTFS' { return 'NTFS' }
        'ReFS' { return 'ReFS' }
        'FAT' { return 'FAT' }
        'FAT32' { return 'FAT32' }
        'exFAT' { return 'exFAT' }
        'UDF' { return 'UDF' }
        'CDFS' { return 'CDFS' }
        default { return $null }
    }
}

function Get-SafeLetter($Value) {
    if ($null -eq $Value -or [string]$Value -eq '' -or [string]$Value -eq [string][char]0) { return $null }
    if ([string]$Value -match '^[a-zA-Z]:?$') { return ([string]$Value).Substring(0, 1).ToUpperInvariant() }
    return 'UNKNOWN'
}

function Get-SafeImageOS($Value) {
    if ([string]$Value -match '^win\d{2}(-vs\d{4})?(-arm64)?$') { return [string]$Value }
    return $null
}

function Get-MountedVolumeExitCode($Snapshot) {
    if ($Snapshot.status -eq 'OBSERVED') { return 0 }
    return 1
}

function Get-MountedVolumeSnapshot {
    param(
        [Parameter(Mandatory)][scriptblock]$StorageProvider,
        [Parameter(Mandatory)][scriptblock]$CimProvider,
        [Parameter(Mandatory)][scriptblock]$DirectoryProvider
    )
    $result = [ordered]@{
        schemaVersion = 1
        status = 'UNKNOWN'
        knownStage = 'providers'
        category = 'missingMetadata'
        identity = $null
        providerCoverage = [ordered]@{
            storage = [ordered]@{ status = 'notAttempted'; rowCount = $null; fixedCount = $null }
            cim = [ordered]@{ status = 'notAttempted'; rowCount = $null; fixedCount = $null }
            directoryAssociations = [ordered]@{ status = 'notAttempted'; queriedFixedCount = 0; directoryMountCount = $null }
            reconciliation = 'UNKNOWN'
        }
        volumes = @()
    }
    $storage = @()
    $cim = @()
    try {
        $storage = @(& $StorageProvider)
        $result.providerCoverage.storage.status = 'observed'
        $result.providerCoverage.storage.rowCount = $storage.Count
    } catch {
        $result.providerCoverage.storage.status = 'failed'
    }
    try {
        $cim = @(& $CimProvider)
        $result.providerCoverage.cim.status = 'observed'
        $result.providerCoverage.cim.rowCount = $cim.Count
    } catch {
        $result.providerCoverage.cim.status = 'failed'
    }
    if ($result.providerCoverage.storage.status -eq 'failed' -or $result.providerCoverage.cim.status -eq 'failed') {
        $result.category = 'providerFailure'
        return $result
    }

    $storageMap = @{}
    $cimMap = @{}
    $invalid = $false
    foreach ($provider in @(
        @{ rows = $storage; map = $storageMap; key = 'Path'; coverage = 'storage' },
        @{ rows = $cim; map = $cimMap; key = 'DeviceID'; coverage = 'cim' }
    )) {
        $fixedCount = 0
        foreach ($row in $provider.rows) {
            $driveType = [string](Get-SafeProperty $row 'DriveType')
            if ($driveType -notin @('2', '3', '4', '5', '6', 'Removable', 'Fixed', 'Remote', 'CD-ROM', 'RAM Disk')) {
                $invalid = $true
                continue
            }
            if ($driveType -notin @('3', 'Fixed')) { continue }
            $fixedCount++
            $key = Get-VolumeKey (Get-SafeProperty $row $provider.key)
            if ($null -eq $key -or $provider.map.ContainsKey($key)) { $invalid = $true; continue }
            $provider.map[$key] = $row
        }
        $result.providerCoverage[$provider.coverage].fixedCount = $fixedCount
    }
    $keys = @(@($storageMap.Keys) + @($cimMap.Keys) | Sort-Object -Unique)
    if ($invalid -or $keys.Count -eq 0) {
        $result.knownStage = 'reconciliation'
        return $result
    }

    $mismatch = $false
    $missing = $false
    $mountFailed = $false
    $mountInvalid = $false
    $totalMounts = 0
    foreach ($key in $keys) {
        $storageRow = $storageMap[$key]
        $cimRow = $cimMap[$key]
        $matched = $null -ne $storageRow -and $null -ne $cimRow
        if (-not $matched) { $mismatch = $true }
        $storageFs = Get-SafeFileSystem (Get-SafeProperty $storageRow 'FileSystem')
        $cimFs = Get-SafeFileSystem (Get-SafeProperty $cimRow 'FileSystem')
        $storageLetter = Get-SafeLetter (Get-SafeProperty $storageRow 'DriveLetter')
        $cimLetter = Get-SafeLetter (Get-SafeProperty $cimRow 'DriveLetter')
        $letterMetadataPresent = $null -ne $storageRow -and $null -ne $cimRow -and
            $null -ne $storageRow.PSObject.Properties['DriveLetter'] -and
            $null -ne $cimRow.PSObject.Properties['DriveLetter']
        if (-not $letterMetadataPresent) { $missing = $true }
        $health = switch ([string](Get-SafeProperty $storageRow 'HealthStatus')) {
            'Healthy' { 'Healthy' }
            '0' { 'Healthy' }
            'Warning' { 'Warning' }
            '1' { 'Warning' }
            'Unhealthy' { 'Unhealthy' }
            '2' { 'Unhealthy' }
            default { $null }
        }
        if ($null -eq $storageFs -or $null -eq $cimFs -or $null -eq $health) { $missing = $true }
        if ($storageFs -ne $cimFs -or $storageLetter -ne $cimLetter -or
            $storageLetter -eq 'UNKNOWN' -or $cimLetter -eq 'UNKNOWN') { $mismatch = $true }
        $directoryCount = $null
        $rowMountInvalid = $false
        if ($null -ne $cimRow) {
            try {
                $directories = @(& $DirectoryProvider $cimRow)
                $result.providerCoverage.directoryAssociations.queriedFixedCount++
                $seen = @{}
                $directoryCount = 0
                foreach ($directory in $directories) {
                    $name = [string](Get-SafeProperty $directory 'Name')
                    if ($name -notmatch '^[a-zA-Z]:\\' -or $name -match '[\x00-\x1f]' -or $seen.ContainsKey($name)) {
                        $mountInvalid = $true
                        $rowMountInvalid = $true
                        $directoryCount = $null
                        break
                    }
                    $seen[$name] = $true
                    if ($name -match '^[a-zA-Z]:\\$') {
                        if ($name.Substring(0, 1).ToUpperInvariant() -ne $cimLetter) {
                            $mountInvalid = $true
                            $rowMountInvalid = $true
                        }
                    } else {
                        $directoryCount++
                    }
                }
                if ($null -ne $directoryCount) { $totalMounts += $directoryCount }
            } catch {
                $mountFailed = $true
                $directoryCount = $null
            }
        }
        if ($rowMountInvalid) { $directoryCount = $null }
        $fileSystem = if ($matched -and $storageFs -eq $cimFs) { $storageFs } else { $null }
        $letterRole = if (-not $matched -or -not $letterMetadataPresent -or
            $storageLetter -ne $cimLetter -or $storageLetter -eq 'UNKNOWN') { $null }
            elseif ($null -eq $storageLetter) { 'unlettered' }
            elseif ($storageLetter -eq 'C') { 'C' } else { 'otherLetter' }
        $result.volumes += [ordered]@{
            status = if ($matched -and $null -ne $fileSystem -and $null -ne $health -and
                $null -ne $letterRole -and $null -ne $directoryCount) { 'observed' } else { 'UNKNOWN' }
            fileSystem = $fileSystem
            driveType = 'Fixed'
            health = $health
            driveLetterRole = $letterRole
            directoryMountCount = $directoryCount
        }
    }
    $result.providerCoverage.directoryAssociations.status = if ($mountFailed) { 'failed' }
        elseif ($mountInvalid) { 'UNKNOWN' } else { 'observed' }
    if (-not $mountFailed -and -not $mountInvalid) {
        $result.providerCoverage.directoryAssociations.directoryMountCount = $totalMounts
    }
    $result.knownStage = 'reconciliation'
    if ($mountFailed) { $result.knownStage = 'directoryAssociations'; $result.category = 'providerFailure' }
    elseif ($mismatch -or $mountInvalid) { $result.category = 'inconsistentMetadata' }
    elseif ($missing) { $result.category = 'missingMetadata' }
    else {
        $result.status = 'OBSERVED'
        $result.category = 'matchedProviderCoverage'
        $result.providerCoverage.reconciliation = 'matched'
    }
    return $result
}

function Invoke-HostedMountedVolumeCollection {
    # No caller-supplied output path: the sole output is a new fixed-name runner-temp file.
    $output = $null
    try {
        if ($env:GITHUB_ACTIONS -ne 'true' -or $env:GITHUB_REPOSITORY -ne 'yeelam-gordon/fastapi' -or
            -not [IO.Path]::IsPathFullyQualified($env:RUNNER_TEMP)) { return 2 }
        $root = Get-Item -LiteralPath $env:RUNNER_TEMP -Force -ErrorAction Stop
        if (-not $root.PSIsContainer -or ($root.Attributes -band [IO.FileAttributes]::ReparsePoint)) { return 2 }
        $output = Join-Path $root.FullName 'p75-mounted-volumes.json'
        if (Test-Path -LiteralPath $output) { return 2 }
    } catch { return 2 }

    $identity = [ordered]@{
        nativeOS = $null; processArchitecture = $null; runnerOS = $null; runnerArchitecture = $null
        imageOS = $null; imageVersion = $null
    }
    $identity.nativeOS = if ([Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [Runtime.InteropServices.OSPlatform]::Windows)) { 'Windows' } else { $null }
    $osArchitecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    $identity.processArchitecture = if ([Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString() -eq 'Arm64') { 'ARM64' } else { $null }
    if ($env:RUNNER_OS -eq 'Windows') { $identity.runnerOS = 'Windows' }
    if ($env:RUNNER_ARCH -eq 'ARM64') { $identity.runnerArchitecture = 'ARM64' }
    $identity.imageOS = Get-SafeImageOS $env:ImageOS
    if ($env:ImageVersion -match '^\d{1,8}(\.\d{1,8}){1,4}$') { $identity.imageVersion = $env:ImageVersion }
    $valid = $identity.nativeOS -eq 'Windows' -and $osArchitecture -eq 'Arm64' -and
        $null -ne $identity.processArchitecture -and $null -ne $identity.runnerOS -and
        $null -ne $identity.runnerArchitecture -and $null -ne $identity.imageOS -and $null -ne $identity.imageVersion
    if ($valid) {
        $result = Get-MountedVolumeSnapshot -StorageProvider {
            Get-Volume -ErrorAction Stop -WarningAction SilentlyContinue
        } -CimProvider {
            Get-CimInstance -Namespace root\cimv2 -ClassName Win32_Volume -ErrorAction Stop -WarningAction SilentlyContinue
        } -DirectoryProvider {
            param($volume)
            Get-CimAssociatedInstance -InputObject $volume -Association Win32_MountPoint -ResultClassName Win32_Directory -ErrorAction Stop -WarningAction SilentlyContinue
        }
    } else {
        $result = Get-MountedVolumeSnapshot -StorageProvider { throw 'not queried' } -CimProvider { throw 'not queried' } -DirectoryProvider { throw 'not queried' }
        $result.knownStage = 'runtimeIdentity'
        $result.category = 'missingMetadata'
        $result.providerCoverage.storage.status = 'notAttempted'
        $result.providerCoverage.cim.status = 'notAttempted'
    }
    $identity['osArchitecture'] = if ($osArchitecture -eq 'Arm64') { 'ARM64' } else { $null }
    $result.identity = $identity
    try {
        $json = ConvertTo-Json -InputObject $result -Depth 8
        $stream = [IO.File]::Open($output, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
            $stream.Write($bytes, 0, $bytes.Length)
        } finally { $stream.Dispose() }
    } catch { return 2 }
    return (Get-MountedVolumeExitCode $result)
}
