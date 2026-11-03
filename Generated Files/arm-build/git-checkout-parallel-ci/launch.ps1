$ErrorActionPreference = 'Stop'
$public = Join-Path $env:GITHUB_WORKSPACE 'checkout-public'
$private = Join-Path $env:GITHUB_WORKSPACE 'checkout-private'
New-Item -ItemType Directory -Path $public -ErrorAction Stop | Out-Null
$category = 'private-storage'
try {
    if ($IsWindows) {
        . (Join-Path $PSScriptRoot '..\hobl-build-etw\private.ps1')
        New-PrivateDirectory $private
    } else {
        # mkdir(mode=0700) via the bootstrap interpreter applies before any raw output.
        & /bin/mkdir -m 700 $private
        if ($LASTEXITCODE) { throw 'Private directory failed' }
        & /bin/chmod 700 $private
        if ($LASTEXITCODE) { throw 'Private permissions failed' }
    }
    $category = 'missing-python'
    $bootstrap = if ($IsWindows) { (Get-Command python -ErrorAction Stop).Source } else {
        (Get-Command python3 -ErrorAction Stop).Source
    }
    $category = 'missing-uv'
    $uv = (Get-Command uv -ErrorAction Stop).Source
    $category = 'native-command'
    $source = Join-Path $env:GITHUB_WORKSPACE 'package-source'
    & $bootstrap -I -B (Join-Path $PSScriptRoot 'screen.py') bootstrap $private $public $source $uv `
        1> (Join-Path $private 'launcher.stdout') 2> (Join-Path $private 'launcher.stderr')
    if ($LASTEXITCODE) { throw 'Closed screen failed' }
    exit 0
} catch {
    $stage = Join-Path $public 'stage.json'
    if (-not (Test-Path -LiteralPath $stage)) {
        @{schema=1;stage='launch';category=$category;native_code=-1} |
            ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath $stage
    }
    $result = Join-Path $public 'result.json'
    if (Test-Path -LiteralPath $result) { Remove-Item -LiteralPath $result }
    exit 1
}
