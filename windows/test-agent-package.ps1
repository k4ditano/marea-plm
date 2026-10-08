param([Parameter(Mandatory = $true)][string]$Package)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'agent-package.ps1')
$Package = (Resolve-Path -LiteralPath $Package).Path
# Do not run lifecycle cleanup against an installed user's package identity.
if (Test-Path -LiteralPath (Join-Path $Package 'unins000.exe')) { throw 'Use an owned test bundle, not an installed package.' }
$cache = Join-Path $Package 'bin/marea-agent-access.txt'
if (Test-Path -LiteralPath $cache) { throw 'Use a fresh owned bundle with no provisioned agent profile.' }
$temporary = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) ('marea-agent-lifecycle-' + [guid]::NewGuid().ToString('N'))))
$tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
if (-not $temporary.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid lifecycle root.' }
[void][IO.Directory]::CreateDirectory($temporary)
$previous = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = $temporary
    $state = Join-Path $temporary 'Marea/Agent'
    [void][IO.Directory]::CreateDirectory($state)
    $marker = Join-Path $state 'keep.txt'
    [IO.File]::WriteAllText($marker, 'keep existing agent state')
    Invoke-MareaAgentMaintenance $Package '--prepare'
    $prepared = [IO.File]::ReadAllText($cache)
    Invoke-MareaAgentMaintenance $Package '--prepare'
    if ([IO.File]::ReadAllText($cache) -ne $prepared) { throw 'Repeated preparation changed the package cache.' }
    Test-MareaAgentPackage $Package
    if ([IO.File]::ReadAllText($cache) -ne $prepared) { throw 'Validation changed the installed profile cache.' }
    if (Test-Path -LiteralPath (Join-Path $Package 'bin/marea-agent-validation-access.txt')) { throw 'Validation cache was not cleaned.' }
    Invoke-MareaAgentMaintenance $Package '--remove-profile'
    Invoke-MareaAgentMaintenance $Package '--remove-profile'
    if (Test-Path -LiteralPath $cache) { throw 'Profile removal left its package cache.' }
    if ([IO.File]::ReadAllText($marker) -ne 'keep existing agent state') { throw 'Package lifecycle changed existing agent state.' }
    Write-Output 'PASS: native SDK preflight, independent profiles, repeat provisioning/removal and agent state preservation; no account or desktop.'
} finally {
    try { Invoke-MareaAgentMaintenance $Package '--remove-profile' }
    finally {
        $env:LOCALAPPDATA = $previous
        Remove-Item -LiteralPath $temporary -Recurse -Force
    }
}
