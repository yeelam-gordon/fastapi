$ErrorActionPreference = 'Stop'
$root = Join-Path (Get-Location) 'Generated Files/arm-build/pipe-matched-ci-readiness/static-files/sourcepins-case'
New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
try {
    $file = Join-Path $root 'input.txt'
    $manifest = Join-Path $root 'pins.json'
    [IO.File]::WriteAllText($file, 'qualified')
    @{files=@{'input.txt'=@{bytes=(Get-Item $file).Length;sha256=(Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant()}}} |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifest
    & (Join-Path $PSScriptRoot 'verify_sourcepins.ps1') -Root $root -Manifest $manifest
    $hidden = Join-Path $root '.gitattributes'
    [IO.File]::WriteAllText($hidden, '* -text')
    if ($IsWindows) {
        [IO.File]::SetAttributes($hidden, [IO.FileAttributes]::Hidden)
    }
    $hiddenRejected = $false
    try { Get-Item -LiteralPath $hidden -ErrorAction Stop | Out-Null }
    catch { $hiddenRejected = $true }
    if (-not $hiddenRejected) { throw 'Fixture did not reproduce hidden-item filtering' }
    $pins = Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json -AsHashtable
    $pins.files['.gitattributes'] = @{
        bytes = ([IO.FileInfo]::new($hidden)).Length
        sha256 = (Get-FileHash -LiteralPath $hidden -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $pins | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifest
    & (Join-Path $PSScriptRoot 'verify_sourcepins.ps1') -Root $root -Manifest $manifest
    [IO.File]::WriteAllText($file, 'corrupted')
    $rejected = $false
    try { & (Join-Path $PSScriptRoot 'verify_sourcepins.ps1') -Root $root -Manifest $manifest }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Corrupt pin was accepted' }
    Remove-Item -LiteralPath $file
    $rejected = $false
    try { & (Join-Path $PSScriptRoot 'verify_sourcepins.ps1') -Root $root -Manifest $manifest }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Missing pin was accepted' }
    Write-Output 'PASS: source-pin gate includes hidden files and rejects corrupt/missing bytes'
}
finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
