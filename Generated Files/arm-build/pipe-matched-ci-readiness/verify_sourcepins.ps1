param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$Manifest
)
$ErrorActionPreference = 'Stop'
$rootPath = [IO.Path]::GetFullPath($Root) + [IO.Path]::DirectorySeparatorChar
$pins = (Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json -AsHashtable).files
if (-not $pins -or $pins.Count -eq 0) { throw 'Empty source pin manifest' }
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($name in $pins.Keys) {
    $relative = $name.Replace('\', '/')
    if (-not $seen.Add($relative) -or [IO.Path]::IsPathRooted($relative) -or
        $relative.Split('/') -contains '..') { throw "Invalid/colliding source pin: $name" }
    $path = [IO.Path]::GetFullPath((Join-Path $Root $relative))
    if (-not $path.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Source pin escaped tool root: $name"
    }
    $pin = $pins[$name]
    if (-not $pin.ContainsKey('bytes') -or
        -not ($pin.bytes -is [int] -or $pin.bytes -is [long]) -or $pin.bytes -lt 0 -or
        $pin.sha256 -notmatch '^[0-9a-f]{64}$' -or
        -not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing/invalid source pin: $name" }
    if ((Get-Item -LiteralPath $path -Force).Length -ne $pin.bytes -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.sha256) {
        throw "Source pin bytes/hash mismatch: $name"
    }
}
Write-Output "PASS: all $($pins.Count) inventoried source files exist and match before setup"
