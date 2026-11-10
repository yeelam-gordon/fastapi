function Select-NvmeDiagnosticScalars {
    param($Record, [string[]]$Fields)
    if ($null -eq $Record) { throw 'Null diagnostic record' }
    $result = [ordered]@{}
    foreach ($name in $Fields) {
        if ($Record -is [System.Collections.IDictionary]) {
            if (-not $Record.Contains($name)) { throw "Missing diagnostic field: $name" }
            $value = $Record[$name]
        } else {
            $property = $Record.PSObject.Properties[$name]
            if ($null -eq $property) { throw "Missing diagnostic field: $name" }
            $value = $property.Value
        }
        if ($value -is [enum] -or $value -is [char]) { $value = $value.ToString() }
        if ($null -ne $value -and $value -isnot [string] -and $value -isnot [bool] -and
            $value -isnot [byte] -and $value -isnot [sbyte] -and
            $value -isnot [int16] -and $value -isnot [uint16] -and
            $value -isnot [int32] -and $value -isnot [uint32] -and
            $value -isnot [int64] -and $value -isnot [uint64]) {
            throw "Non-scalar diagnostic field: $name"
        }
        if ($value -is [string] -and $value.Length -gt 1024) {
            throw "Oversized diagnostic field: $name"
        }
        $result[$name] = $value
    }
    return ,$result
}

function ConvertTo-NvmeDiagnosticJson {
    param($Context, $Inventory)
    $contextFields = @('GitHubActions', 'RunnerEnvironment', 'RunnerOS', 'RunnerArch',
        'Repository', 'RunAttempt', 'ActualOS', 'ActualOSArchitecture')
    $fields = [ordered]@{
        Disks = @('Number', 'UniqueId', 'BusType', 'PartitionStyle', 'NumberOfPartitions',
            'Size', 'IsBoot', 'IsSystem', 'IsOffline', 'IsReadOnly')
        Partitions = @('DiskNumber', 'DriveLetter')
        Volumes = @('DriveLetter', 'FileSystem', 'Size', 'SizeRemaining')
        Drives = @('Name')
    }
    $projected = [ordered]@{}
    foreach ($name in $fields.Keys) {
        $items = Get-NvmeField $Inventory $name
        if ($items -isnot [array] -or $items.Count -gt 128) {
            throw "Invalid or oversized diagnostic inventory: $name"
        }
        $projected[$name] = @(foreach ($item in $items) {
            Select-NvmeDiagnosticScalars $item $fields[$name]
        })
    }
    $plain = [ordered]@{
        context = Select-NvmeDiagnosticScalars $Context $contextFields
        inventory = $projected
    }
    $json = $plain | ConvertTo-Json -Depth 5 -Compress -WarningAction Stop
    $bytes = [Text.Encoding]::UTF8.GetByteCount($json)
    if ($bytes -gt 65536) { throw 'Diagnostic JSON exceeds 64 KiB' }
    return @{ Json = $json; Utf8Bytes = $bytes; Depth = 5 }
}
