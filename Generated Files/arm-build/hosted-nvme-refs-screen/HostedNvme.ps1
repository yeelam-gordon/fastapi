function Get-NvmeField {
    param($Record, [string]$Name)
    if ($Record -is [System.Collections.IDictionary]) {
        return ,$Record[$Name]
    }
    if ($null -ne $Record -and $null -ne $Record.PSObject.Properties[$Name]) {
        return ,$Record.PSObject.Properties[$Name].Value
    }
    return $null
}

function Test-NvmeInteger {
    param($Value)
    return ($Value -is [byte] -or $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64]) -and $Value -ge 0
}

function New-NvmeSkip {
    param([string]$Reason)
    [pscustomobject]@{ Status = 'Skipped'; Reason = $Reason; BenchmarkEligible = $false }
}

function Test-NvmeContext {
    param($Context)
    foreach ($gate in @(
        @('GitHubActions', 'true'), @('RunnerEnvironment', 'github-hosted'),
        @('RunnerOS', 'Windows'), @('RunnerArch', 'ARM64'),
        @('Repository', 'yeelam-gordon/fastapi'), @('RunAttempt', '1'),
        @('ActualOS', 'Windows'), @('ActualOSArchitecture', 'Arm64')
    )) {
        $value = Get-NvmeField $Context $gate[0]
        if ($value -isnot [string] -or $value -cne $gate[1]) {
            return New-NvmeSkip "Context:$($gate[0])"
        }
    }
    [pscustomobject]@{ Status = 'Qualified' }
}

function Test-NvmeMetadata {
    param($Context, $Inventory)
    $gate = Test-NvmeContext $Context
    if ($gate.Status -eq 'Skipped') { return $gate }
    foreach ($name in @('Disks', 'Partitions', 'Volumes', 'Drives')) {
        $items = Get-NvmeField $Inventory $name
        if ($items -isnot [array] -or @($items | Where-Object { $null -eq $_ }).Count) {
            return New-NvmeSkip "Inventory:$name"
        }
    }
    foreach ($partition in $Inventory.Partitions) {
        if (-not (Test-NvmeInteger (Get-NvmeField $partition 'DiskNumber'))) {
            return New-NvmeSkip 'Inventory:PartitionDiskNumber'
        }
    }
    foreach ($view in @('Partitions', 'Volumes', 'Drives')) {
        foreach ($item in $Inventory.$view) {
            $field = if ($view -eq 'Drives') { 'Name' } else { 'DriveLetter' }
            $hasField = if ($item -is [System.Collections.IDictionary]) {
                $item.Contains($field)
            } else { $null -ne $item.PSObject.Properties[$field] }
            $letter = Get-NvmeField $item $field
            # Null/zero drive letters are the Storage API's unassigned representation.
            if (-not $hasField -or
                ($null -ne $letter -and $letter -isnot [string] -and $letter -isnot [char]) -or
                ($view -eq 'Drives' -and [string]::IsNullOrWhiteSpace([string]$letter))) {
                return New-NvmeSkip "Inventory:$view-letter"
            }
            if ([string]$letter -ieq 'D') { return New-NvmeSkip "OccupiedD:$view" }
            if ($view -ne 'Drives' -and $null -ne $letter -and
                [string]$letter -notmatch '^(?:[A-Za-z]|\x00)?$') {
                return New-NvmeSkip "Inventory:$view-letter"
            }
        }
    }
    $candidates = @()
    foreach ($disk in $Inventory.Disks) {
        foreach ($name in @('Number', 'NumberOfPartitions', 'Size')) {
            if (-not (Test-NvmeInteger (Get-NvmeField $disk $name))) {
                return New-NvmeSkip "Disk:$name"
            }
        }
        foreach ($name in @('IsOffline', 'IsReadOnly', 'IsBoot', 'IsSystem')) {
            if ((Get-NvmeField $disk $name) -isnot [bool]) {
                return New-NvmeSkip "Disk:$name"
            }
        }
        $identity = Get-NvmeField $disk 'UniqueId'
        if ($identity -isnot [string] -or [string]::IsNullOrWhiteSpace($identity)) {
            return New-NvmeSkip 'Disk:UniqueId'
        }
        foreach ($name in @('BusType', 'PartitionStyle')) {
            $value = Get-NvmeField $disk $name
            if (($value -isnot [string] -and $value -isnot [enum]) -or
                [string]::IsNullOrWhiteSpace([string]$value)) {
                return New-NvmeSkip "Disk:$name"
            }
        }
        if ([string]$disk.BusType -ceq 'NVMe' -and [string]$disk.PartitionStyle -ceq 'RAW' -and
            -not $disk.IsOffline -and -not $disk.IsReadOnly -and
            -not $disk.IsBoot -and -not $disk.IsSystem -and
            $disk.NumberOfPartitions -eq 0 -and $disk.Size -ge 50GB -and
            $disk.Number -notin @($Inventory.Partitions | ForEach-Object { $_.DiskNumber })) {
            $candidates += $disk
        }
    }
    if ($candidates.Count -ne 1) { return New-NvmeSkip "CandidateCount:$($candidates.Count)" }
    [pscustomobject]@{ Status = 'Qualified'; Disk = $candidates[0] }
}

function Get-NvmeContext {
    @{
        GitHubActions = $env:GITHUB_ACTIONS
        RunnerEnvironment = $env:RUNNER_ENVIRONMENT
        RunnerOS = $env:RUNNER_OS
        RunnerArch = $env:RUNNER_ARCH
        Repository = $env:GITHUB_REPOSITORY
        RunAttempt = $env:GITHUB_RUN_ATTEMPT
        ActualOS = if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
            [System.Runtime.InteropServices.OSPlatform]::Windows)) { 'Windows' } else { 'Other' }
        ActualOSArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    }
}

function Get-NvmeInventory {
    @{
        Disks = @(Get-Disk -ErrorAction Stop)
        Partitions = @(Get-Partition -ErrorAction Stop)
        Volumes = @(Get-Volume -ErrorAction Stop)
        Drives = @(Get-PSDrive -PSProvider FileSystem -ErrorAction Stop)
    }
}

function Invoke-HostedNvmePreparation {
    [CmdletBinding()]
    param([switch]$Provision)
    $ErrorActionPreference = 'Stop'
    if (-not $Provision) { return New-NvmeSkip 'ProvisionNotRequested' }
    $context = Get-NvmeContext
    $gate = Test-NvmeContext $context
    if ($gate.Status -eq 'Skipped') { return $gate }
    $qualified = Test-NvmeMetadata $context (Get-NvmeInventory)
    if ($qualified.Status -eq 'Skipped') { return $qualified }
    # Capture scalars, not a mutable reference to a CIM observation.
    $number = $qualified.Disk.Number
    $identity = $qualified.Disk.UniqueId
    $size = $qualified.Disk.Size
    $context = Get-NvmeContext
    $fresh = Test-NvmeMetadata $context (Get-NvmeInventory)
    if ($fresh.Status -eq 'Skipped') { return $fresh }
    if ($fresh.Disk.Number -ne $number -or $fresh.Disk.UniqueId -cne $identity -or
        $fresh.Disk.Size -ne $size) { return New-NvmeSkip 'DiskIdentityChanged' }
    $initialized = Initialize-Disk -InputObject $fresh.Disk -PartitionStyle GPT -PassThru -ErrorAction Stop
    $partition = $initialized | New-Partition -UseMaximumSize -DriveLetter D -ErrorAction Stop
    $null = $partition | Format-Volume -FileSystem ReFS -NewFileSystemLabel 'HostedCache' -Confirm:$false -ErrorAction Stop
    $volumes = @(Get-Volume -DriveLetter D -ErrorAction Stop)
    $partitions = @(Get-Partition -DriveLetter D -ErrorAction Stop)
    if ($volumes.Count -ne 1 -or $partitions.Count -ne 1 -or
        (Get-NvmeField $volumes[0] 'FileSystem') -cne 'ReFS' -or
        [string](Get-NvmeField $volumes[0] 'DriveLetter') -cne 'D' -or
        (Get-NvmeField $partitions[0] 'DiskNumber') -ne $number -or
        [string](Get-NvmeField $partitions[0] 'DriveLetter') -cne 'D') {
        throw 'Provisioned volume verification failed'
    }
    $root = "D:\hosted-cache-$([guid]::NewGuid().ToString('N'))"
    $null = New-Item -ItemType Directory -Path $root -ErrorAction Stop
    $cache = "$root\cache"
    $temp = "$root\temp"
    $null = New-Item -ItemType Directory -Path $cache, $temp -ErrorAction Stop
    [pscustomobject]@{
        Status = 'Prepared'; Reason = 'OrdinaryReFS'; BenchmarkEligible = $true
        DiskNumber = $number; DiskUniqueId = $identity
        CacheDirectory = $cache; TempDirectory = $temp
    }
}
