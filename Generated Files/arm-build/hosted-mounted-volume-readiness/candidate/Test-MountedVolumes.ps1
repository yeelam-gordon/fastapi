$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'Collect-MountedVolumes.ps1')

function Assert-Case([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

# Every provider is synthetic; the hosted entry point is never invoked.
$storageC = [pscustomobject]@{
    Path = '\\?\Volume{11111111-1111-1111-1111-111111111111}\'
    DriveType = 'Fixed'; DriveLetter = 'C'; FileSystem = 'NTFS'; HealthStatus = 'Healthy'
    FileSystemLabel = 'PRIVATE-LABEL'; UniqueId = 'PRIVATE-ID'
}
$cimC = [pscustomobject]@{
    DeviceID = $storageC.Path; DriveType = 3; DriveLetter = 'C:'; FileSystem = 'NTFS'
    Label = 'PRIVATE-LABEL'; SerialNumber = 'PRIVATE-SERIAL'
}
$storageOther = [pscustomobject]@{
    Path = '\\?\Volume{22222222-2222-2222-2222-222222222222}\'
    DriveType = 'Fixed'; DriveLetter = $null; FileSystem = 'ReFS'; HealthStatus = 'Healthy'
}
$cimOther = [pscustomobject]@{
    DeviceID = $storageOther.Path; DriveType = 3; DriveLetter = $null; FileSystem = 'ReFS'
}
$lettered = Get-MountedVolumeSnapshot -StorageProvider { $storageC } -CimProvider { $cimC } -DirectoryProvider {
    [pscustomobject]@{ Name = 'C:\' }
}
Assert-Case ($lettered.status -eq 'OBSERVED' -and $lettered.volumes.Count -eq 1 -and
    $lettered.volumes[0].fileSystem -eq 'NTFS' -and $lettered.volumes[0].directoryMountCount -eq 0) 'Lettered NTFS/root association'

$mounted = Get-MountedVolumeSnapshot -StorageProvider { $storageC; $storageOther } -CimProvider { $cimC; $cimOther } -DirectoryProvider {
    param($volume)
    if ($null -eq $volume.DriveLetter) {
        [pscustomobject]@{ Name = 'C:\PRIVATE-MOUNT' }
        [pscustomobject]@{ Name = 'C:\PRIVATE-SECOND-MOUNT' }
    } else { [pscustomobject]@{ Name = 'C:\' } }
}
$unlettered = @($mounted.volumes | Where-Object driveLetterRole -EQ 'unlettered')
Assert-Case ($mounted.status -eq 'OBSERVED' -and $unlettered.Count -eq 1 -and
    $unlettered[0].fileSystem -eq 'ReFS' -and $unlettered[0].directoryMountCount -eq 2 -and
    $mounted.providerCoverage.directoryAssociations.queriedFixedCount -eq 2) 'Unlettered volume and existing directory mounts'

$missingStorage = [pscustomobject]@{ Path = $storageOther.Path; DriveType = 'Fixed'; DriveLetter = $null }
$missing = Get-MountedVolumeSnapshot -StorageProvider { $missingStorage } -CimProvider { $cimOther } -DirectoryProvider { }
Assert-Case ($missing.status -eq 'UNKNOWN' -and $null -eq $missing.volumes[0].fileSystem -and
    $null -eq $missing.volumes[0].health) 'Missing fields stay null'

$rawStorage = [pscustomobject]@{ Path = $storageOther.Path; DriveType = 'Fixed'; DriveLetter = $null; FileSystem = 'RAW'; HealthStatus = 'Healthy' }
$raw = Get-MountedVolumeSnapshot -StorageProvider { $rawStorage } -CimProvider { $cimOther } -DirectoryProvider { }
Assert-Case ($raw.status -eq 'UNKNOWN' -and $null -eq $raw.volumes[0].fileSystem) 'Unformatted volume is unknown'

$storageFailure = Get-MountedVolumeSnapshot -StorageProvider { throw 'PRIVATE-ERROR' } -CimProvider { $cimC } -DirectoryProvider { throw 'must not query' }
Assert-Case ($storageFailure.status -eq 'UNKNOWN' -and $storageFailure.category -eq 'providerFailure' -and
    $storageFailure.providerCoverage.storage.status -eq 'failed' -and $storageFailure.providerCoverage.cim.status -eq 'observed') 'Storage failure boundary'
$cimFailure = Get-MountedVolumeSnapshot -StorageProvider { $storageC } -CimProvider { throw 'PRIVATE-ERROR' } -DirectoryProvider { throw 'must not query' }
Assert-Case ($cimFailure.status -eq 'UNKNOWN' -and $cimFailure.providerCoverage.cim.status -eq 'failed') 'CIM failure boundary'
$mountFailure = Get-MountedVolumeSnapshot -StorageProvider { $storageC } -CimProvider { $cimC } -DirectoryProvider { throw 'PRIVATE-ERROR' }
Assert-Case ($mountFailure.status -eq 'UNKNOWN' -and $mountFailure.knownStage -eq 'directoryAssociations' -and
    $mountFailure.providerCoverage.directoryAssociations.status -eq 'failed' -and $null -eq $mountFailure.volumes[0].directoryMountCount) 'Association failure boundary'

$mismatch = Get-MountedVolumeSnapshot -StorageProvider { $storageC; $storageOther } -CimProvider { $cimC } -DirectoryProvider { }
Assert-Case ($mismatch.status -eq 'UNKNOWN' -and $mismatch.category -eq 'inconsistentMetadata' -and
    $mismatch.volumes.Count -eq 2 -and $mismatch.providerCoverage.reconciliation -eq 'UNKNOWN') 'Provider fixed-set mismatch'
$empty = Get-MountedVolumeSnapshot -StorageProvider { } -CimProvider { } -DirectoryProvider { }
Assert-Case ($empty.status -eq 'UNKNOWN') 'Empty result is never success'
$invalidMount = Get-MountedVolumeSnapshot -StorageProvider { $storageC } -CimProvider { $cimC } -DirectoryProvider { [pscustomobject]@{ Name = $null } }
Assert-Case ($invalidMount.status -eq 'UNKNOWN' -and $null -eq $invalidMount.providerCoverage.directoryAssociations.directoryMountCount) 'Invalid association metadata'

$duplicate = Get-MountedVolumeSnapshot -StorageProvider { $storageC; $storageC } -CimProvider { $cimC } -DirectoryProvider { }
Assert-Case ($duplicate.status -eq 'UNKNOWN') 'Duplicate join identifiers'
$differentFs = [pscustomobject]@{ DeviceID = $storageC.Path; DriveType = 3; DriveLetter = 'C:'; FileSystem = 'ReFS' }
$different = Get-MountedVolumeSnapshot -StorageProvider { $storageC } -CimProvider { $differentFs } -DirectoryProvider { }
Assert-Case ($different.status -eq 'UNKNOWN' -and $null -eq $different.volumes[0].fileSystem) 'Filesystem mismatch'
$unknownType = [pscustomobject]@{ Path = $storageC.Path; DriveType = $null }
$unknownDrive = Get-MountedVolumeSnapshot -StorageProvider { $unknownType } -CimProvider { $cimC } -DirectoryProvider { }
Assert-Case ($unknownDrive.status -eq 'UNKNOWN') 'Unknown drive type cannot disappear'
$wrongRoot = Get-MountedVolumeSnapshot -StorageProvider { $storageC } -CimProvider { $cimC } -DirectoryProvider { [pscustomobject]@{ Name = 'D:\' } }
Assert-Case ($wrongRoot.status -eq 'UNKNOWN' -and $wrongRoot.volumes[0].status -eq 'UNKNOWN') 'Root association disagreement'

$missingLetterStorage = [pscustomobject]@{ Path = $storageOther.Path; DriveType = 'Fixed'; FileSystem = 'ReFS'; HealthStatus = 'Healthy' }
$missingLetterCim = [pscustomobject]@{ DeviceID = $storageOther.Path; DriveType = 3; FileSystem = 'ReFS' }
$missingLetter = Get-MountedVolumeSnapshot -StorageProvider { $missingLetterStorage } -CimProvider { $missingLetterCim } -DirectoryProvider { }
Assert-Case ($missingLetter.status -eq 'UNKNOWN' -and $missingLetter.category -eq 'missingMetadata' -and
    $null -eq $missingLetter.volumes[0].driveLetterRole) 'Missing letter fields are not evidence of an unlettered volume'
Assert-Case ((Get-SafeImageOS 'win11-vs2026-arm64') -eq 'win11-vs2026-arm64' -and
    (Get-SafeImageOS 'win11-arm64') -eq 'win11-arm64' -and
    $null -eq (Get-SafeImageOS 'win11-PRIVATE-IMAGE')) 'Known hosted image family and privacy guard'

$snapshots = @($lettered, $mounted, $missing, $raw, $storageFailure, $cimFailure, $mountFailure, $mismatch, $empty, $invalidMount, $duplicate, $different, $unknownDrive, $wrongRoot, $missingLetter)
foreach ($snapshot in $snapshots) {
    $expectedExit = if ($snapshot.status -eq 'OBSERVED') { 0 } else { 1 }
    Assert-Case ((Get-MountedVolumeExitCode $snapshot) -eq $expectedExit) 'Shared exit mapping'
}
$json = $snapshots | ConvertTo-Json -Depth 10
Assert-Case ($json -notmatch 'PRIVATE|Volume\{|DeviceID|UniqueId|SerialNumber|FileSystemLabel|11111111|22222222') 'Privacy projection'
$roundTrip = $mounted | ConvertTo-Json -Depth 8 | ConvertFrom-Json
Assert-Case (($roundTrip.PSObject.Properties.Name -join ',') -eq 'schemaVersion,status,knownStage,category,identity,providerCoverage,volumes') 'Top-level schema'
Assert-Case (($roundTrip.volumes[0].PSObject.Properties.Name -join ',') -eq 'status,fileSystem,driveType,health,driveLetterRole,directoryMountCount') 'Volume field allowlist'
Write-Output 'PASS: 16 synthetic cases; privacy, schema and exit checks; no live providers or hosted entry point invoked.'
