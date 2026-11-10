[CmdletBinding()]
param([switch]$Provision)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'HostedNvme.ps1')
Invoke-HostedNvmePreparation -Provision:$Provision
