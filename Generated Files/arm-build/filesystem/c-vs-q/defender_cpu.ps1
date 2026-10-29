param([ValidateSet("before", "after")][string]$Phase)
$record = [ordered]@{
    phase = $Phase
    utc = [DateTime]::UtcNow.ToString("o")
    status = "unknown"
    aggregate_cpu_seconds = $null
    scope = "Shared-host MsMpEng process CPU only; not attributable blocked-scan wall time."
}
try {
    $processes = @(Get-Process -Name MsMpEng -ErrorAction Stop)
    $values = @($processes | ForEach-Object { $_.CPU })
    if ($values.Count -eq $processes.Count -and $values.Count -gt 0 -and
        @($values | Where-Object { $null -eq $_ }).Count -eq 0) {
        $record.status = "available"
        $record.aggregate_cpu_seconds = ($values | Measure-Object -Sum).Sum
    }
} catch {
    $record.status = "unknown-absent-or-denied"
}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot "MsMpEng-$Phase.json")
$record | ConvertTo-Json
