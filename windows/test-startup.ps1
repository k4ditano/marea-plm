$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../tools/startup.ps1') -Library
$token = [Guid]::NewGuid().ToString('N')
$testRoot = 'Software\Pleamar\Tests\Startup-' + $token
$approvalRoot = $testRoot + '\Approval'
$temporary = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) ('Marea startup ñ ' + $token)))
if (-not $temporary.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid temporary path.' }
function Check($Value, $Message) { if (-not $Value) { throw $Message } }
function Invoke-Test($Action) { Invoke-MareaStartup -Package $temporary -Action $Action -RegistryRoot $testRoot -ApprovalRoot $approvalRoot }
try {
    Check ((Invoke-Test state).reason -eq 'installed-only') 'Source profile must not register startup.'
    $null = New-Item -ItemType Directory -Path (Join-Path $temporary 'windows')
    Set-Content -LiteralPath (Join-Path $temporary 'windows/desktop.ps1') -Value '# owned fixture, never executed'
    Set-Content -LiteralPath (Join-Path $temporary 'package.json') -Value '{"app_id":"A8D741A8-45D5-4DE8-A38E-27DA65D253F8"}'
    Check (-not (Invoke-Test state).enabled) 'Startup should be opt-in.'
    Check ((Invoke-Test enable).enabled) 'Enable did not read back.'
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey(($testRoot + '\Run'), $true)
    try {
        $command = $key.GetValue('Marea')
        Check ($command.Contains('-File "' + (Join-Path $temporary 'windows/desktop.ps1') + '" start')) 'Space/Unicode path quoting failed.'
        $key.SetValue('Unrelated', 'preserve')
    } finally { $key.Dispose() }
    Check ((Invoke-Test enable).enabled) 'Repeated enable failed.'
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($approvalRoot)
    try { $key.SetValue('Marea', [byte[]]@(3,0,0,0,0,0,0,0,0,0,0,0), [Microsoft.Win32.RegistryValueKind]::Binary) } finally { $key.Dispose() }
    $state = Invoke-Test state
    Check ($state.blocked -and -not $state.enabled -and $state.registered) 'Windows disable was hidden.'
    Check (-not (Invoke-Test disable).registered) 'Disable did not remove registration.'
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey(($testRoot + '\Run'), $true)
    try { Check ($key.GetValue('Unrelated') -eq 'preserve') 'Unrelated value changed.'; $key.SetValue('Marea', 'another-installation') } finally { $key.Dispose() }
    Check ((Invoke-Test enable).reason -eq 'another-installation') 'Foreign registration was replaced.'
    Check ((Invoke-Test disable).reason -eq 'another-installation') 'Foreign registration was removed.'
    Write-Output 'PASS: isolated HKCU startup opt-in/out, readback, idempotence, Unicode quoting, OS disable and ownership'
} finally {
    # Only the exact owned fixture registry subtree and verified temporary path.
    [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($testRoot, $false)
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
