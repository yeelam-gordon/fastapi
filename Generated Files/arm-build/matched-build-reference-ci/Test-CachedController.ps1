$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Cached-Controller.ps1')
function Assert-CacheFailure([scriptblock]$Operation, [string]$Pattern) {
    try { & $Operation } catch {
        if ($_.Exception.Message -like $Pattern) { return }
        throw
    }
    throw "Expected rejection: $Pattern"
}
function New-SyntheticImage([string]$Root, [string]$Version, [int]$Machine = 0xAA64) {
    $directory = Join-Path $Root "Python\$Version\arm64"
    $null = New-Item -ItemType Directory -Path $directory -Force
    $bytes = [byte[]]::new(128)
    [BitConverter]::GetBytes([uint16]0x5A4D).CopyTo($bytes, 0)
    [BitConverter]::GetBytes([uint32]64).CopyTo($bytes, 60)
    [BitConverter]::GetBytes([uint32]0x4550).CopyTo($bytes, 64)
    [BitConverter]::GetBytes([uint16]$Machine).CopyTo($bytes, 68)
    [IO.File]::WriteAllBytes((Join-Path $directory 'python.exe'), $bytes)
    [IO.File]::WriteAllBytes((Join-Path $directory 'python313.dll'), $bytes)
    [IO.File]::WriteAllBytes((Join-Path (Split-Path $directory) 'arm64.complete'), [byte[]]::new(0))
    return $directory
}
$root = Join-Path $PSScriptRoot ('test-cache-' + [guid]::NewGuid().ToString('N'))
try {
    $null = New-Item -ItemType Directory -Path (Join-Path $root 'Python') -Force
    Assert-CacheFailure { Select-CachedController $root } '*Missing or ambiguous*'
    $directory = New-SyntheticImage $root '3.13.17'
    $candidate = Select-CachedController $root
    if ($candidate.Version -cne '3.13.17' -or $candidate.Directory -cne $directory) {
        throw 'Cached normal patch selection failed'
    }
    Remove-Item -LiteralPath (Join-Path (Split-Path $directory) 'arm64.complete')
    Assert-CacheFailure { Select-CachedController $root } '*does not exist*'
    $null = New-SyntheticImage $root '3.13.17' 0x8664
    Assert-CacheFailure { Select-CachedController $root } '*not native ARM64*'
    $null = New-SyntheticImage $root '3.13.17'
    [IO.File]::WriteAllBytes((Join-Path $directory 'python313t.dll'), [byte[]]::new(0))
    Assert-CacheFailure { Select-CachedController $root } '*Non-normal*'
    Remove-Item -LiteralPath (Join-Path $directory 'python313t.dll')
    $null = New-SyntheticImage $root '3.13.15'
    Assert-CacheFailure { Select-CachedController $root } '*ambiguous*'
    Remove-Item -LiteralPath (Join-Path $root 'Python\3.13.15') -Recurse -Force
    $null = New-SyntheticImage $root '3.13.18rc1'
    if ((Select-CachedController $root).Version -cne '3.13.17') { throw 'Prerelease selected' }
    foreach ($number in 0..30) {
        $null = New-Item -ItemType Directory -Path (Join-Path $root "Python\unrelated-$number")
    }
    Assert-CacheFailure { Select-CachedController $root } '*candidate bound exceeded*'
    Write-Output 'PASS: cached-only synthetic image selection, misses, incomplete/non-native/non-normal/ambiguous/bounded candidates; no interpreter executed'
} finally {
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
