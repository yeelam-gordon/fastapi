function Assert-ControllerRegularPath {
    param([string]$Path, [switch]$Directory)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        $item.PSIsContainer -ne $Directory.IsPresent) { throw "Invalid cache path type: $Path" }
    return $item
}

function Assert-ControllerArm64PE {
    param([string]$Path)
    $item = Assert-ControllerRegularPath $Path
    if ($item.Length -lt 70 -or $item.Length -gt 64MB) { throw 'Invalid cached PE size' }
    $stream = [IO.File]::OpenRead($Path)
    $reader = [IO.BinaryReader]::new($stream)
    try {
        if ($reader.ReadUInt16() -ne 0x5A4D) { throw 'Cached executable is not PE' }
        $stream.Position = 60
        $offset = $reader.ReadUInt32()
        if ($offset -lt 64 -or $offset -gt $stream.Length - 6) { throw 'Cached PE offset' }
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0xAA64) {
            throw 'Cached executable is not native ARM64'
        }
    } finally { $reader.Dispose(); $stream.Dispose() }
}

function Select-CachedController {
    param([string]$Root)
    if (-not [IO.Path]::IsPathFullyQualified($Root)) { throw 'Absolute RUNNER_TOOL_CACHE required' }
    $rootPath = [IO.Path]::GetFullPath($Root)
    $ancestor = $rootPath
    while ($ancestor) {
        $null = Assert-ControllerRegularPath $ancestor -Directory
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    $pythonRoot = Join-Path $rootPath 'Python'
    $null = Assert-ControllerRegularPath $pythonRoot -Directory
    $entries = @(Get-ChildItem -LiteralPath $pythonRoot -Directory -Force | Select-Object -First 33)
    if ($entries.Count -gt 32) { throw 'Cached image candidate bound exceeded' }
    $candidates = @()
    foreach ($entry in $entries) {
        if ($entry.Name -cnotmatch '^3\.13\.(0|[1-9][0-9]*)$') { continue }
        $null = Assert-ControllerRegularPath $entry.FullName -Directory
        $directory = Join-Path $entry.FullName 'arm64'
        if (-not (Test-Path -LiteralPath $directory)) { continue }
        $null = Assert-ControllerRegularPath $directory -Directory
        $null = Assert-ControllerRegularPath (Join-Path $entry.FullName 'arm64.complete')
        foreach ($name in @('python313t.dll', 'python313_d.dll', 'python_d.exe')) {
            if (Test-Path -LiteralPath (Join-Path $directory $name)) { throw 'Non-normal cached Python' }
        }
        $python = Join-Path $directory 'python.exe'
        Assert-ControllerArm64PE $python
        Assert-ControllerArm64PE (Join-Path $directory 'python313.dll')
        $candidates += @{ Python = $python; Directory = $directory; Version = $entry.Name }
    }
    if ($candidates.Count -ne 1) { throw 'Missing or ambiguous complete normal ARM64 Python 3.13 cache' }
    return $candidates[0]
}
