$ErrorActionPreference = 'Stop'
$watch = [Diagnostics.Stopwatch]::StartNew()
$root = Join-Path $env:GITHUB_WORKSPACE 'paired-reference'
New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
$python = $env:PAIRED_MAC_PYTHON
$receipt = @{ version = '3.12.10'; components = @{}; distribution = 'actions/setup-python arm64' }
if ($env:RUNNER_OS -eq 'Windows') {
    $receipt.distribution = 'PSF official portable ARM64 ZIP'
    $receipt.url = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-arm64.zip'
    $zip = Join-Path $root 'python.zip'
    Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-arm64.zip' -OutFile $zip
    if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne '20a5b1a707d899ffdfc5e3086d7372f7cc95eeea344d48ae256047cb7075cf63') {
        throw 'Official portable CPython ZIP hash mismatch'
    }
    $receipt.zip_sha256 = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    $distribution = Join-Path $root 'python'
    Expand-Archive -LiteralPath $zip -DestinationPath $distribution
    $python = Join-Path $distribution 'python.exe'
    foreach ($pair in @(
        @($python, '7f1ebbbb04164caf8f8073aafa7f82321fb44695e10fe6a9ebaf2138b63892c4'),
        @((Join-Path $distribution 'python312.dll'), '84df280a69e539107d2537b36ef1ff6e67713634a5c374c96a600da86939e98f')
    )) {
        if ((Get-FileHash $pair[0] -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pair[1]) {
            throw 'Official portable CPython component hash mismatch'
        }
        $bytes = [IO.File]::ReadAllBytes($pair[0])
        $offset = [BitConverter]::ToInt32($bytes, 60)
        if ([BitConverter]::ToUInt16($bytes, $offset + 4) -ne 0xAA64) {
            throw 'Refusing non-native ARM64 PE before invocation'
        }
        $receipt.components[[IO.Path]::GetFileName($pair[0])] = @{
            sha256 = (Get-FileHash $pair[0] -Algorithm SHA256).Hash.ToLowerInvariant()
            pe_machine = '0xaa64'
        }
    }
}
if (-not $python -or -not (Test-Path -LiteralPath $python)) { throw 'Absolute native Python required' }
if ($env:RUNNER_OS -eq 'macOS') {
    $slices = & /usr/bin/lipo -archs $python
    if ($LASTEXITCODE -or $slices -notmatch '\barm64\b') {
        throw 'Mach-O must contain ARM64 before invocation (universal2 is valid)'
    }
}
"PAIRED_PYTHON=$python" | Out-File -Append -Encoding utf8 $env:GITHUB_ENV
"PAIRED_ROOT=$root" | Out-File -Append -Encoding utf8 $env:GITHUB_ENV
$helper = Join-Path $PSScriptRoot 'driver.py'
& $python $helper --root $root --guard-only
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$watch.Stop()
$receipt.bootstrap_seconds = $watch.Elapsed.TotalSeconds
$receipt | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $root 'bootstrap-download.json')
