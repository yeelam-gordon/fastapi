function Get-GitHubQueueAgeSeconds {
    param(
        [Parameter(Mandatory)][string]$CreatedAt,
        [Parameter(Mandatory)][string]$ServerDate
    )
    $culture = [Globalization.CultureInfo]::InvariantCulture
    $style = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
    $server = [DateTimeOffset]::ParseExact($ServerDate, 'r', $culture, $style)
    $created = [DateTimeOffset]::Parse($CreatedAt, $culture, $style)
    $age = ($server - $created).TotalSeconds
    if ($age -lt 0) { throw 'GitHub server date predates run creation; no cancellation justified' }
    return $age
}

function Test-GitHubQueueBound {
    param(
        [Parameter(Mandatory)][double]$AgeSeconds,
        [Parameter(Mandatory)][string[]]$JobStatuses
    )
    return $AgeSeconds -gt 300 -and $JobStatuses -contains 'queued'
}
