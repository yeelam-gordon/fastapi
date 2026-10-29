param(
    [string]$Python = 'C:\Program Files\Python313-arm64\python.exe',
    [string]$Wheelhouse
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$tools = Join-Path $root 'tools'
$uv = Join-Path $tools 'uv.exe'
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

& $Python -c "import platform; assert platform.machine().lower() in ('arm64', 'aarch64'), 'Native ARM64 Python required'"
if ($LASTEXITCODE -ne 0) { throw 'A working native ARM64 Python is required' }

if (-not (Test-Path -LiteralPath $uv)) {
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    $archive = Join-Path $tools 'uv-aarch64-pc-windows-msvc-0.13.6.zip'
    Invoke-WebRequest 'https://github.com/astral-sh/uv/releases/download/0.13.6/uv-aarch64-pc-windows-msvc.zip' -OutFile $archive
    $expected = 'c2426c0c8e28b53d8c440e47a18d96ad4db51e159866c0e81435b196d7f0081c'
    if ((Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant() -ne $expected) {
        throw 'Official uv archive SHA256 mismatch'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $tools
}
& $uv --version
if ($LASTEXITCODE -ne 0) { throw 'uv execution failed' }

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $uv venv --python $Python (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'ARM64 environment creation failed' }
}
$install = @('pip', 'install', '--python', $venvPython, '--require-hashes', '--only-binary', ':all:',
    '--requirements', (Join-Path $root 'tooling.lock'))
if ($Wheelhouse) {
    $install += @('--no-index', '--find-links', (Resolve-Path -LiteralPath $Wheelhouse).Path)
}
& $uv @install
if ($LASTEXITCODE -ne 0) { throw 'Tool installation failed; network failures must be resolved or an offline wheelhouse supplied' }
& $venvPython -c "import build, psutil, platform, sys; print(sys.version); print(platform.machine()); print('build', build.__version__); print('psutil', psutil.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'Installed tool verification failed' }
