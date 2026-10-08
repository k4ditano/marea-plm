param([ValidateSet('state','enable','disable')][string]$Action = 'state', [switch]$Library)
$ErrorActionPreference = 'Stop'

# Only our per-user entry is touched. StartupApproved is read, never modified:
# a Task Manager/policy disable must be visible instead of reported as success.
function Invoke-MareaStartup {
    param([string]$Package, [string]$Action,
        [string]$RegistryRoot = 'Software\Microsoft\Windows\CurrentVersion',
        [string]$ApprovalRoot = 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run')
    $packagePath = [IO.Path]::GetFullPath($Package)
    $launcher = Join-Path $packagePath 'windows/desktop.ps1'
    $manifest = Join-Path $packagePath 'package.json'
    if (-not (Test-Path -LiteralPath $launcher) -or -not (Test-Path -LiteralPath $manifest)) {
        return @{available=$false; enabled=$false; blocked=$false; reason='installed-only'}
    }
    $identity = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if ($identity.app_id -ne 'A8D741A8-45D5-4DE8-A38E-27DA65D253F8') { throw 'Unexpected package identity.' }
    $hostBinary = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $command = '"' + $hostBinary + '" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '" start'
    $keyPath = $RegistryRoot + '\Run'
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($keyPath, $Action -ne 'state')
    try {
        $existing = if ($key) { $key.GetValue('Marea', $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) } else { $null }
        if ($null -ne $existing -and $existing -cne $command) {
            return @{available=$false; enabled=$false; blocked=$false; reason='another-installation'}
        }
        if ($Action -eq 'enable') {
            if (-not $key) { $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($keyPath) }
            $key.SetValue('Marea', $command, [Microsoft.Win32.RegistryValueKind]::String)
        } elseif ($Action -eq 'disable' -and $key) { $key.DeleteValue('Marea', $false) }
        $registered = $key -and ($key.GetValue('Marea') -ceq $command)
    } finally { if ($key) { $key.Dispose() } }
    $approval = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($ApprovalRoot)
    try { $status = $null; if ($approval) { $status = $approval.GetValue('Marea') } }
    finally { if ($approval) { $approval.Dispose() } }
    # 2/6 are enabled entries. Unknown states are not assumed to be enabled.
    $blocked = $registered -and $status -is [byte[]] -and ($status.Length -lt 1 -or $status[0] -notin @(2,6))
    return @{available=$true; enabled=[bool]$registered -and -not $blocked; registered=[bool]$registered;
        blocked=[bool]$blocked; reason=$(if ($blocked) {'disabled-by-windows'} else {''})}
}

if (-not $Library) {
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
    # Installed as app/tools/startup.ps1. Source runs deliberately cannot opt in.
    try {
        Invoke-MareaStartup -Package (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Action $Action | ConvertTo-Json -Compress
    } catch {
        @{available=$false; enabled=$false; blocked=$false; reason='error'; error=$_.Exception.Message} | ConvertTo-Json -Compress
        exit 1
    }
}
