param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$stage = 10
try {
    if ([IO.Directory]::Exists($Root) -or [IO.File]::Exists($Root)) { exit 2 }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $sids = @($identity.User.Value, $system.Value) | Select-Object -Unique
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($identity.User)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in $sids) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($sid),
            'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    $stage = 11
    [IO.FileSystemAclExtensions]::CreateDirectory($acl, $Root) | Out-Null
    $stage = 12
    $item = Get-Item -LiteralPath $Root -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { exit $stage }
    $stage = 13
    if (@(Get-ChildItem -LiteralPath $Root -Force).Count -ne 0) { exit $stage }
    $stage = 15
    $actual = Get-Acl -LiteralPath $Root
    if (-not $actual.AreAccessRulesProtected) { exit $stage }
    $stage = 14
    if ($actual.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $identity.User.Value) { exit $stage }
    $stage = 16
    $rules = @($actual.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne $sids.Count) { exit $stage }
    foreach ($rule in $rules) {
        if ($rule.IsInherited -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl -or
            $rule.InheritanceFlags -ne ([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit) -or
            $rule.PropagationFlags -ne [Security.AccessControl.PropagationFlags]::None -or
            $rule.IdentityReference.Value -notin $sids) { exit $stage }
    }
    if (@($rules.IdentityReference.Value | Select-Object -Unique).Count -ne $sids.Count) { exit $stage }
    Write-Output 'P63_PRIVATE_ROOT_VERIFIED'
    exit 0
} catch { exit $stage }
