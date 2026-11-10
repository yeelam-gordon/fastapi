$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'HostedNvme.ps1')
. (Join-Path $PSScriptRoot 'Storage-Diagnostic.ps1')
function Assert-Diagnostic($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Assert-DiagnosticFailure([scriptblock]$Operation, [string]$Pattern) {
    try { & $Operation } catch {
        if ($_.Exception.Message -like $Pattern) { return }
        throw
    }
    throw "Expected rejection: $Pattern"
}
$context = @{
    GitHubActions = 'true'; RunnerEnvironment = 'github-hosted'; RunnerOS = 'Windows'
    RunnerArch = 'ARM64'; Repository = 'yeelam-gordon/fastapi'; RunAttempt = '1'
    ActualOS = 'Windows'; ActualOSArchitecture = 'Arm64'
}
$script:unneededReads = 0
$disk = [pscustomobject]@{
    Number = 7; UniqueId = 'synthetic-unused'; BusType = 'NVMe'; PartitionStyle = 'RAW'
    NumberOfPartitions = 0; Size = [uint64](64GB)
    IsBoot = $false; IsSystem = $false; IsOffline = $false; IsReadOnly = $false
}
$disk | Add-Member ScriptProperty CimClass { $script:unneededReads++; return $this }
$drive = [pscustomobject]@{ Name = 'C' }
$provider = [pscustomobject]@{ Drives = @($drive) }
$drive | Add-Member NoteProperty ProviderGraph $provider
$drive | Add-Member ScriptProperty Unneeded { $script:unneededReads++; throw 'Graph visited' }
$inventory = @{
    Disks = @($disk)
    Partitions = @([pscustomobject]@{ DiskNumber = 0; DriveLetter = [char]'C' })
    Volumes = @([pscustomobject]@{
        DriveLetter = [char]'C'; FileSystem = 'NTFS'; Size = [uint64](128GB); SizeRemaining = [uint64](64GB)
    })
    Drives = @($drive)
}
$diagnostic = ConvertTo-NvmeDiagnosticJson $context $inventory
$decoded = $diagnostic.Json | ConvertFrom-Json
Assert-Diagnostic ($script:unneededReads -eq 0) 'Unneeded CIM/provider graph was visited'
Assert-Diagnostic ([object]::ReferenceEquals($provider.Drives[0], $drive)) 'Self-reference fixture missing'
Assert-Diagnostic ($diagnostic.Utf8Bytes -le 65536 -and $diagnostic.Depth -eq 5) 'Unbounded JSON'
Assert-Diagnostic ($diagnostic.Utf8Bytes -eq [Text.Encoding]::UTF8.GetByteCount($diagnostic.Json)) 'Byte count'
foreach ($key in $context.Keys) {
    Assert-Diagnostic ($decoded.context.$key -ceq $context[$key]) "Context lost: $key"
}
foreach ($key in @('Number', 'UniqueId', 'BusType', 'PartitionStyle', 'NumberOfPartitions',
    'Size', 'IsBoot', 'IsSystem', 'IsOffline', 'IsReadOnly')) {
    Assert-Diagnostic ($decoded.inventory.Disks[0].$key -ceq $disk.$key) "Disk field lost: $key"
}
Assert-Diagnostic (@($decoded.inventory.Disks[0].PSObject.Properties).Count -eq 10) 'Unselected disk graph retained'
Assert-Diagnostic ($decoded.inventory.Partitions[0].DiskNumber -eq 0 -and
    $decoded.inventory.Partitions[0].DriveLetter -ceq 'C') 'Partition fields lost'
Assert-Diagnostic ($decoded.inventory.Volumes[0].FileSystem -ceq 'NTFS' -and
    $decoded.inventory.Volumes[0].DriveLetter -ceq 'C' -and
    $decoded.inventory.Volumes[0].Size -eq 128GB -and
    $decoded.inventory.Volumes[0].SizeRemaining -eq 64GB) 'Volume fields lost'
Assert-Diagnostic ($decoded.inventory.Drives[0].Name -ceq 'C') 'Drive name lost'
$before = Test-NvmeMetadata $context $inventory
$after = Test-NvmeMetadata $decoded.context $decoded.inventory
Assert-Diagnostic ($before.Status -ceq 'Qualified' -and $after.Status -ceq 'Qualified' -and
    $after.Disk.UniqueId -ceq $disk.UniqueId) 'Unchanged safety eligibility lost'
$disk.IsBoot = $true
Assert-Diagnostic ((Test-NvmeMetadata $context $inventory).Status -ceq 'Skipped') 'Boot disk accepted'
$rejected = (ConvertTo-NvmeDiagnosticJson $context $inventory).Json | ConvertFrom-Json
Assert-Diagnostic ((Test-NvmeMetadata $rejected.context $rejected.inventory).Status -ceq 'Skipped') 'Boot flag lost'
Assert-DiagnosticFailure { Select-NvmeDiagnosticScalars @{} @('DriveLetter') } '*Missing diagnostic field*'
Assert-DiagnosticFailure { Select-NvmeDiagnosticScalars @{Size = $disk} @('Size') } '*Non-scalar*'
Assert-DiagnosticFailure { Select-NvmeDiagnosticScalars @{Name = ('x' * 1025)} @('Name') } '*Oversized*'
$scalars = Select-NvmeDiagnosticScalars @{
    Letter = [char]0; Kind = [IO.DriveType]::Fixed; Empty = $null
} @('Letter', 'Kind', 'Empty')
Assert-Diagnostic ($scalars.Letter -ceq ([char]0).ToString() -and $scalars.Kind -ceq 'Fixed' -and
    $scalars.Contains('Empty') -and $null -eq $scalars.Empty) 'Character/enum/null value changed'
$inventory.Drives = @($drive) * 129
Assert-DiagnosticFailure { ConvertTo-NvmeDiagnosticJson $context $inventory } '*oversized diagnostic inventory*'
$inventory.Drives = @([pscustomobject]@{Name = ('x' * 1024)}) * 128
Assert-DiagnosticFailure { ConvertTo-NvmeDiagnosticJson $context $inventory } '*JSON exceeds 64 KiB*'
Write-Output 'PASS: scalar fields, graph non-traversal, unchanged safety gates and bounds; synthetic only'
