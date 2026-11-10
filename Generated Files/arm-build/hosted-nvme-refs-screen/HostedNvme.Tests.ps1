$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$library = Join-Path $PSScriptRoot 'HostedNvme.ps1'
$tokens = $null
$parseErrors = $null
$syntax = [System.Management.Automation.Language.Parser]::ParseFile(
    $library, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count) { throw 'library-parser-errors' }
foreach ($file in @($PSCommandPath, (Join-Path $PSScriptRoot 'Prepare-HostedNvme.ps1'))) {
    $null = [System.Management.Automation.Language.Parser]::ParseFile(
        $file, [ref]$tokens, [ref]$parseErrors
    )
    if ($parseErrors.Count) { throw "parser-errors:$file" }
}
foreach ($statement in $syntax.EndBlock.Statements) {
    if ($statement -isnot [System.Management.Automation.Language.FunctionDefinitionAst]) {
        throw 'library-must-only-define-functions'
    }
}
# Any newly introduced command must be reviewed before this harness can execute it.
$allowedCommands = @(
    'Get-NvmeField', 'Test-NvmeInteger', 'New-NvmeSkip', 'Test-NvmeContext',
    'Test-NvmeMetadata', 'Get-NvmeContext', 'Get-NvmeInventory',
    'Where-Object', 'ForEach-Object', 'Get-Disk', 'Get-Partition', 'Get-Volume',
    'Get-PSDrive', 'Initialize-Disk', 'New-Partition', 'Format-Volume', 'New-Item'
)
foreach ($command in $syntax.FindAll({
    param($node) $node -is [System.Management.Automation.Language.CommandAst]
}, $true)) {
    if ($command.GetCommandName() -cnotin $allowedCommands) {
        throw "unreviewed-library-command:$($command.Extent.Text)"
    }
}
. $library

function New-SyntheticFixture {
    @{
        Context = @{
            GitHubActions = 'true'; RunnerEnvironment = 'github-hosted'
            RunnerOS = 'Windows'; RunnerArch = 'ARM64'
            Repository = 'yeelam-gordon/fastapi'; RunAttempt = '1'
            ActualOS = 'Windows'; ActualOSArchitecture = 'Arm64'
        }
        Inventory = @{
            Disks = @([pscustomobject]@{
                Number = 7; UniqueId = 'SYNTHETIC-NOT-A-REAL-DISK'; Size = 50GB
                BusType = 'NVMe'; PartitionStyle = 'RAW'; NumberOfPartitions = 0
                IsOffline = $false; IsReadOnly = $false; IsBoot = $false; IsSystem = $false
            })
            Partitions = @([pscustomobject]@{ DiskNumber = 0; DriveLetter = 'C' })
            Volumes = @([pscustomobject]@{ DriveLetter = 'C' })
            Drives = @([pscustomobject]@{ Name = 'C' })
        }
    }
}

$script:CaseCount = 0
function Assert-Test {
    param([bool]$Condition, [string]$Name)
    if (-not $Condition) { throw "FAIL:$Name" }
}
function Assert-Skipped {
    param($Result, [string]$Name)
    Assert-Test ($Result.Status -ceq 'Skipped' -and
        $Result.BenchmarkEligible -eq $false -and
        -not [string]::IsNullOrWhiteSpace($Result.Reason)) $Name
}

$fixture = New-SyntheticFixture
Assert-Test ((Test-NvmeMetadata $fixture.Context $fixture.Inventory).Status -eq 'Qualified') 'positive-metadata'
$script:CaseCount++
foreach ($key in @('GitHubActions', 'RunnerEnvironment', 'RunnerOS', 'RunnerArch',
    'Repository', 'RunAttempt', 'ActualOS', 'ActualOSArchitecture')) {
    foreach ($mutation in @('Missing', 'Null', 'Wrong')) {
        $fixture = New-SyntheticFixture
        switch ($mutation) {
            'Missing' { $fixture.Context.Remove($key) }
            'Null' { $fixture.Context[$key] = $null }
            'Wrong' { $fixture.Context[$key] = 'self-hosted-or-wrong' }
        }
        Assert-Skipped (Test-NvmeMetadata $fixture.Context $fixture.Inventory) "context-$key-$mutation"
        $script:CaseCount++
    }
}

$cases = @(
    @{ Name = 'occupied-partition'; Change = { param($f) $f.Inventory.Partitions[0].DriveLetter = 'D' } }
    @{ Name = 'occupied-volume'; Change = { param($f) $f.Inventory.Volumes[0].DriveLetter = 'd' } }
    @{ Name = 'occupied-psdrive'; Change = { param($f) $f.Inventory.Drives[0].Name = 'D' } }
    @{ Name = 'multiple-disks'; Change = { param($f) $f.Inventory.Disks += $f.Inventory.Disks[0] } }
    @{ Name = 'no-disks'; Change = { param($f) $f.Inventory.Disks = @() } }
    @{ Name = 'partition-inventory-entry'; Change = { param($f) $f.Inventory.Partitions[0].DiskNumber = 7 } }
    @{ Name = 'partition-count'; Change = { param($f) $f.Inventory.Disks[0].NumberOfPartitions = 1 } }
    @{ Name = 'small'; Change = { param($f) $f.Inventory.Disks[0].Size = 50GB - 1 } }
    @{ Name = 'not-raw'; Change = { param($f) $f.Inventory.Disks[0].PartitionStyle = 'GPT' } }
    @{ Name = 'not-nvme'; Change = { param($f) $f.Inventory.Disks[0].BusType = 'SATA' } }
    @{ Name = 'offline'; Change = { param($f) $f.Inventory.Disks[0].IsOffline = $true } }
    @{ Name = 'readonly'; Change = { param($f) $f.Inventory.Disks[0].IsReadOnly = $true } }
    @{ Name = 'boot'; Change = { param($f) $f.Inventory.Disks[0].IsBoot = $true } }
    @{ Name = 'system'; Change = { param($f) $f.Inventory.Disks[0].IsSystem = $true } }
    @{ Name = 'missing-letter'; Change = { param($f) $f.Inventory.Volumes[0].PSObject.Properties.Remove('DriveLetter') } }
    @{ Name = 'malformed-letter'; Change = { param($f) $f.Inventory.Volumes[0].DriveLetter = 'D:' } }
    @{ Name = 'missing-partition-disk'; Change = { param($f) $f.Inventory.Partitions[0].PSObject.Properties.Remove('DiskNumber') } }
    @{ Name = 'fractional-number'; Change = { param($f) $f.Inventory.Disks[0].Number = 7.5 } }
    @{ Name = 'negative-size'; Change = { param($f) $f.Inventory.Disks[0].Size = -1 } }
    @{ Name = 'string-false'; Change = { param($f) $f.Inventory.Disks[0].IsBoot = 'false' } }
    @{ Name = 'rerun'; Change = { param($f) $f.Context.RunAttempt = '2' } }
    @{ Name = 'wrong-repository'; Change = { param($f) $f.Context.Repository = 'other/fastapi' } }
    @{ Name = 'x64-runner'; Change = { param($f) $f.Context.RunnerArch = 'X64' } }
    @{ Name = 'x64-os-arm64-runner'; Change = { param($f) $f.Context.ActualOSArchitecture = 'X64' } }
)
foreach ($case in $cases) {
    $fixture = New-SyntheticFixture
    & $case.Change $fixture
    Assert-Skipped (Test-NvmeMetadata $fixture.Context $fixture.Inventory) $case.Name
    $script:CaseCount++
}
foreach ($key in @('Number', 'UniqueId', 'Size', 'BusType', 'PartitionStyle',
    'NumberOfPartitions', 'IsOffline', 'IsReadOnly', 'IsBoot', 'IsSystem')) {
    foreach ($mutation in @('Missing', 'Null', 'Malformed')) {
        $fixture = New-SyntheticFixture
        $disk = $fixture.Inventory.Disks[0]
        switch ($mutation) {
            'Missing' { $disk.PSObject.Properties.Remove($key) }
            'Null' { $disk.$key = $null }
            'Malformed' { $disk.$key = if ($key -eq 'UniqueId') { ' ' } else { 'unknown' } }
        }
        Assert-Skipped (Test-NvmeMetadata $fixture.Context $fixture.Inventory) "disk-$key-$mutation"
        $script:CaseCount++
    }
}
foreach ($key in @('Disks', 'Partitions', 'Volumes', 'Drives')) {
    foreach ($mutation in @('Missing', 'Null', 'Malformed')) {
        $fixture = New-SyntheticFixture
        switch ($mutation) {
            'Missing' { $fixture.Inventory.Remove($key) }
            'Null' { $fixture.Inventory[$key] = $null }
            'Malformed' { $fixture.Inventory[$key] = @($null) }
        }
        Assert-Skipped (Test-NvmeMetadata $fixture.Context $fixture.Inventory) "inventory-$key-$mutation"
        $script:CaseCount++
    }
}

# All Storage reads and writes resolve to these functions, never installed cmdlets.
function Get-NvmeContext {
    $script:ContextReads++
    if ($script:ContextRace -and $script:ContextReads -eq 2) {
        $script:Context.RunAttempt = '2'
    }
    $script:Context
}
function Get-Disk {
    [CmdletBinding()] param()
    $script:Calls.Add('Read')
    $script:Reads++
    if ($script:Failure -eq 'Inventory') { throw 'synthetic-inventory-failure' }
    if ($script:Reads -eq 1) { $script:First.Disks } else { $script:Second.Disks }
}
function Get-Partition {
    [CmdletBinding()] param([string]$DriveLetter)
    if ($DriveLetter) { return [pscustomobject]@{ DiskNumber = 7; DriveLetter = 'D' } }
    if ($script:Reads -eq 1) { $script:First.Partitions } else { $script:Second.Partitions }
}
function Get-Volume {
    [CmdletBinding()] param([string]$DriveLetter)
    if ($DriveLetter) {
        $filesystem = if ($script:Failure -eq 'Verification') { 'NTFS' } else { 'ReFS' }
        return [pscustomobject]@{ FileSystem = $filesystem; DriveLetter = 'D' }
    }
    if ($script:Reads -eq 1) { $script:First.Volumes } else { $script:Second.Volumes }
}
function Get-PSDrive {
    [CmdletBinding()] param([string]$PSProvider)
    if ($script:Reads -eq 1) { $script:First.Drives } else { $script:Second.Drives }
}
function Initialize-Disk {
    [CmdletBinding()] param($InputObject, [string]$PartitionStyle, [switch]$PassThru)
    Assert-Test ($script:Reads -eq 2 -and $InputObject -eq $script:Second.Disks[0] -and
        $PartitionStyle -ceq 'GPT' -and $PassThru) 'initialize-fresh-inputobject'
    $script:Calls.Add('Initialize:GPT')
    if ($script:Failure -eq 'Initialize') { throw 'synthetic-initialize-failure' }
    $InputObject
}
function New-Partition {
    [CmdletBinding()] param(
        [Parameter(ValueFromPipeline)]$InputObject, [switch]$UseMaximumSize, [string]$DriveLetter
    )
    process {
        Assert-Test ($UseMaximumSize -and $DriveLetter -ceq 'D' -and $InputObject.Number -eq 7) 'new-partition-arguments'
        $script:Calls.Add('Partition:D')
        if ($script:Failure -eq 'Partition') { throw 'synthetic-partition-failure' }
        [pscustomobject]@{ DiskNumber = 7; DriveLetter = 'D' }
    }
}
function Format-Volume {
    [CmdletBinding()] param(
        [Parameter(ValueFromPipeline)]$InputObject, [string]$FileSystem,
        [string]$NewFileSystemLabel, [bool]$Confirm
    )
    process {
        Assert-Test ($FileSystem -ceq 'ReFS' -and -not $Confirm -and
            $InputObject.DiskNumber -eq 7) 'ordinary-refs-arguments'
        $script:Calls.Add('Format:ReFS')
        if ($script:Failure -eq 'Format') { throw 'synthetic-format-failure' }
        [pscustomobject]@{ FileSystem = 'ReFS'; DriveLetter = 'D' }
    }
}
function New-Item {
    [CmdletBinding()] param([string]$ItemType, [string[]]$Path)
    foreach ($directory in $Path) {
        Assert-Test ($ItemType -ceq 'Directory' -and
            $directory -cmatch '^D:\\hosted-cache-[0-9a-f]{32}(\\(?:cache|temp))?$') 'fresh-directories-only'
        $script:Calls.Add('Directory')
    }
    if ($script:Failure -eq 'Directory') { throw 'synthetic-directory-failure' }
}
foreach ($name in @('Get-Disk', 'Get-Partition', 'Get-Volume', 'Get-PSDrive',
    'Initialize-Disk', 'New-Partition', 'Format-Volume', 'New-Item')) {
    Assert-Test ((Get-Command $name).CommandType -eq 'Function') "mock-installed-$name"
}
function Reset-MockedExecution {
    $first = New-SyntheticFixture
    $second = New-SyntheticFixture
    $script:Context = $first.Context
    $script:First = $first.Inventory
    $script:Second = $second.Inventory
    $script:Reads = 0
    $script:ContextReads = 0
    $script:ContextRace = $false
    $script:Calls = [System.Collections.Generic.List[string]]::new()
    $script:Failure = ''
}

Reset-MockedExecution
Assert-Skipped (Invoke-HostedNvmePreparation) 'default-refusal'
Assert-Test ($script:Calls.Count -eq 0) 'default-no-inventory'
$script:CaseCount++
Reset-MockedExecution
$script:Context.RunnerEnvironment = 'self-hosted'
Assert-Skipped (Invoke-HostedNvmePreparation -Provision) 'hosted-context-refusal'
Assert-Test ($script:Calls.Count -eq 0) 'context-no-inventory'
$script:CaseCount++

foreach ($race in @('Identity', 'Number', 'Size', 'OccupiedD', 'Unsafe', 'Ambiguous', 'Context')) {
    Reset-MockedExecution
    switch ($race) {
        'Identity' { $script:Second.Disks[0].UniqueId = 'SYNTHETIC-REPLACEMENT' }
        'Number' { $script:Second.Disks[0].Number = 8 }
        'Size' { $script:Second.Disks[0].Size = 51GB }
        'OccupiedD' { $script:Second.Drives[0].Name = 'D' }
        'Unsafe' { $script:Second.Disks[0].IsSystem = $true }
        'Ambiguous' { $script:Second.Disks += $script:Second.Disks[0] }
        'Context' { $script:ContextRace = $true }
    }
    Assert-Skipped (Invoke-HostedNvmePreparation -Provision) "requery-$race"
    Assert-Test (($script:Calls -join ',') -ceq 'Read,Read') "race-no-writes-$race"
    $script:CaseCount++
}
foreach ($failureStage in @('Inventory', 'Initialize', 'Partition', 'Format', 'Verification', 'Directory')) {
    Reset-MockedExecution
    $script:Failure = $failureStage
    $exception = $null
    $result = $null
    try { $result = Invoke-HostedNvmePreparation -Provision }
    catch { $exception = $_.Exception.Message }
    Assert-Test ($null -ne $exception -and $null -eq $result) "fatal-$failureStage"
    if ($failureStage -eq 'Format') {
        Assert-Test (($script:Calls -join ',') -ceq 'Read,Read,Initialize:GPT,Partition:D,Format:ReFS') 'format-failure-no-fallback'
    }
    $script:CaseCount++
}
Reset-MockedExecution
$result = Invoke-HostedNvmePreparation -Provision
Assert-Test ($result.Status -ceq 'Prepared' -and $result.BenchmarkEligible -eq $true -and
    $result.CacheDirectory -cmatch '^D:\\hosted-cache-[0-9a-f]{32}\\cache$' -and
    $result.TempDirectory -cmatch '^D:\\hosted-cache-[0-9a-f]{32}\\temp$') 'prepared-result'
Assert-Test (($script:Calls -join ',') -ceq
    'Read,Read,Initialize:GPT,Partition:D,Format:ReFS,Directory,Directory,Directory') 'positive-call-sequence'
$script:CaseCount++
"PASS: $script:CaseCount cases; parser: 3 files; native formats: 0; native inventory: 0"
