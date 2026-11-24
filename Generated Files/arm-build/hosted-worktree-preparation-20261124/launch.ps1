$ErrorActionPreference = 'Stop'
$public = Join-Path $env:GITHUB_WORKSPACE 'worktree-public'
New-Item -ItemType Directory -Path $public -ErrorAction Stop | Out-Null
$category = 'private-storage'
$ownsPrivate = $false
$code = 1
try {
    if (-not $IsWindows -or -not $env:LOCALAPPDATA) { throw 'Missing Windows local storage' }
    $private = Join-Path $env:LOCALAPPDATA ("wta-" + [guid]::NewGuid().ToString('N').Substring(0, 12))
    if ([IO.Path]::GetPathRoot($private) -ine 'C:\') { throw 'Wrong volume' }
    $helper = Join-Path $PSScriptRoot '..\hobl-build-etw\private.ps1'
    if ((Get-FileHash -LiteralPath $helper -Algorithm SHA256).Hash -ne
        'B8F3164F4BAD5CFF0BB162802BF8DDDE3FB99D69EFE38FD1EA44906978565F72') { throw 'Helper mismatch' }
    . $helper
    New-PrivateDirectory $private
    $ownsPrivate = $true
    $category = 'missing-python'
    $bootstrap = (Get-Command python -CommandType Application -ErrorAction Stop).Source
    $category = 'missing-uv'
    $uv = (Get-Command uv -ErrorAction Stop).Source
    $category = 'native-command'
    $source = Join-Path $env:GITHUB_WORKSPACE 'package-source'
    & $bootstrap -I -B (Join-Path $PSScriptRoot 'screen.py') bootstrap $private $public $source $uv `
        1> (Join-Path $private 'launcher.stdout') 2> (Join-Path $private 'launcher.stderr')
    if ($LASTEXITCODE) { throw 'Closed screen failed' }
    $code = 0
} catch {
    $stage = Join-Path $public 'stage.json'
    if (-not (Test-Path -LiteralPath $stage)) {
        @{schema=1;stage='launch';category=$category;native_code=-1} |
            ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath $stage
    }
    $result = Join-Path $public 'result.json'
    if (Test-Path -LiteralPath $result) { Remove-Item -LiteralPath $result }
} finally {
    if ($ownsPrivate) {
        try {
            Remove-Item -LiteralPath $private -Recurse -Force -ErrorAction Stop
        } catch {
            $code = 1
            Remove-Item -LiteralPath (Join-Path $public 'result.json') -Force -ErrorAction SilentlyContinue
            @{schema=1;stage='launch';category='private-cleanup';native_code=-1} |
                ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath (Join-Path $public 'stage.json')
        }
    }
}
exit $code
