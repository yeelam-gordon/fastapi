param([Parameter(Mandatory)][string]$Before)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'HostedNvme.ps1')
$record = Get-Content -Raw -LiteralPath $Before | ConvertFrom-Json
$gate = Test-NvmeMetadata $record.context $record.inventory
if ($gate.Status -cne 'Qualified') { throw 'Raw retained storage eligibility differs' }
$gate.Disk | Select-Object Number, UniqueId | ConvertTo-Json -Compress
