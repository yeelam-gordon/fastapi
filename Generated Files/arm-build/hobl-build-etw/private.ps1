$ErrorActionPreference = 'Stop'
function New-PrivateDirectory([string] $Path) {
    if (Test-Path -LiteralPath $Path) { throw 'Private destination already exists' }
    $security = [Security.AccessControl.DirectorySecurity]::new()
    $security.SetAccessRuleProtection($true, $false)
    $owner = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $security.SetOwner($owner)
    foreach ($sid in @($owner, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $security.AddAccessRule($rule)
    }
    $info = [IO.DirectoryInfo]::new($Path)
    [IO.FileSystemAclExtensions]::Create($info, $security)
    $actual = [IO.FileSystemAclExtensions]::GetAccessControl($info)
    $rules = $actual.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])
    $actualOwner = $actual.GetOwner([Security.Principal.SecurityIdentifier])
    if (-not $actual.AreAccessRulesProtected -or $rules.Count -ne 2 -or $actualOwner -ne $owner) {
        throw 'Private ACL verification failed'
    }
    foreach ($rule in $rules) {
        if ($rule.IsInherited -or $rule.AccessControlType -ne 'Allow' -or
            $rule.IdentityReference.Value -notin @($owner.Value, 'S-1-5-18') -or
            $rule.FileSystemRights -ne 'FullControl') { throw 'Private ACL rule mismatch' }
    }
}
