param(
    [string]$PleamarBinary = (Join-Path $PSScriptRoot '../pleamar/target/release/pleamar.exe'),
    [string]$DerivaWorkerBinary = (Join-Path $PSScriptRoot 'deriva/target/release/deriva-worker.exe'),
    [string]$AgentHostBinary = (Join-Path $PSScriptRoot 'windows/agent-host/target/release/marea-agent.exe'),
    [string]$WindowManagerBinary = (Join-Path $PSScriptRoot '../pleamar-wm/target/release/pleamar-wm.exe'),
    [string]$WindowManagerHost = (Join-Path $PSScriptRoot '../pleamar-wm/target/release/pleamar-wm-host.exe'),
    [string]$WindowManagerLicense = (Join-Path $PSScriptRoot '../pleamar-wm/LICENSE'),
    [string]$NodeDirectory = (Join-Path $PSScriptRoot '.tools/installer-tools/node-v22.23.3-win-x64'),
    [string]$Prefix = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Marea Windows')
)
$ErrorActionPreference = 'Stop'
$PleamarBinary = (Resolve-Path -LiteralPath $PleamarBinary).Path
$NotificationBrokerBinary = (Resolve-Path -LiteralPath (Join-Path (Split-Path $PleamarBinary -Parent) 'pleamar-notifications.exe')).Path
$WindowManagerBinary = (Resolve-Path -LiteralPath $WindowManagerBinary).Path
$WindowManagerHost = (Resolve-Path -LiteralPath $WindowManagerHost).Path
$WindowManagerLicense = (Resolve-Path -LiteralPath $WindowManagerLicense).Path
. (Join-Path $PSScriptRoot 'windows/runtime-files.ps1')
. (Join-Path $PSScriptRoot 'windows/agent-package.ps1')
$runtimeFiles = Get-PleamarRuntimeFiles $PleamarBinary
$agentFiles = Get-MareaAgentFiles $AgentHostBinary $NodeDirectory
$Prefix = [IO.Path]::GetFullPath($Prefix)
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'Marea Windows.lnk'
# Detect an incomplete source package before creating an installation folder.
foreach ($relative in @('marea.plm', 'marea.luau', 'LICENSE', 'common', 'lang', 'wardrobe', 'shaders', 'assets', 'assets/marea.ico', 'tools/reservas', 'tools/software.ps1', 'windows/prepare-winget.py', 'windows/desktop.ps1', 'windows/run-desktop.ps1', 'windows/shortcuts.ps1', 'windows/runtime_probe.py', 'windows/DESKTOP.md')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $relative))) { throw "Missing packaged input: $relative" }
}
if (Test-Path -LiteralPath $Prefix) { throw "Target already exists: $Prefix. Choose another -Prefix to preserve it." }
if (Test-Path -LiteralPath $shortcutPath) { throw "Shortcut already exists: $shortcutPath" }
. (Join-Path $PSScriptRoot 'windows/shortcuts.ps1')
python (Join-Path $PSScriptRoot 'windows/runtime_probe.py') --binary $PleamarBinary
if ($LASTEXITCODE -ne 0) { throw 'The native pleamar runtime check failed; no installation was created.' }
$DerivaWorkerBinary = (Resolve-Path -LiteralPath $DerivaWorkerBinary).Path
python (Join-Path $PSScriptRoot 'windows/test-deriva-native.py') --worker $DerivaWorkerBinary
if ($LASTEXITCODE -ne 0) { throw 'The Deriva worker failed its isolated library check; no installation was created.' }
python (Join-Path $PSScriptRoot 'windows/build-desktop.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not generate the desktop profile.' }
python (Join-Path $PSScriptRoot 'windows/prepare-winget.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the verified WinGet client; no installation was created.' }
& $PleamarBinary --check (Join-Path $PSScriptRoot 'marea-desktop.plm')
if ($LASTEXITCODE -ne 0) { throw 'The desktop profile did not compile.' }
Test-MareaAgentFiles $agentFiles
foreach ($folder in @('app', 'app/tools', 'bin', 'windows', 'logs')) {
    New-Item -ItemType Directory -Force (Join-Path $Prefix $folder) | Out-Null
}
Copy-Item -LiteralPath $PleamarBinary -Destination (Join-Path $Prefix 'bin/pleamar.exe')
Copy-Item -LiteralPath $NotificationBrokerBinary -Destination (Join-Path $Prefix 'bin/pleamar-notifications.exe')
Copy-Item -LiteralPath $DerivaWorkerBinary -Destination (Join-Path $Prefix 'bin/deriva-worker.exe')
Copy-Item -LiteralPath $WindowManagerBinary -Destination (Join-Path $Prefix 'bin/pleamar-wm.exe')
Copy-Item -LiteralPath $WindowManagerHost -Destination (Join-Path $Prefix 'bin/pleamar-wm-host.exe')
New-Item -ItemType Directory -Force (Join-Path $Prefix 'bin/licenses/pleamar-wm') | Out-Null
Copy-Item -LiteralPath $WindowManagerLicense -Destination (Join-Path $Prefix 'bin/licenses/pleamar-wm/LICENSE')
foreach ($relative in $runtimeFiles.Keys) {
    $destination = Join-Path $Prefix $relative
    New-Item -ItemType Directory -Force (Split-Path $destination -Parent) | Out-Null
    Copy-Item -LiteralPath $runtimeFiles[$relative] -Destination $destination
}
foreach ($relative in $agentFiles.Keys) {
    $destination = Join-Path $Prefix $relative
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
    [IO.File]::Copy($agentFiles[$relative], $destination)
}
foreach ($item in @('marea.plm', 'marea.luau', 'marea-desktop.plm', 'marea-desktop.luau', 'LICENSE', 'common', 'lang', 'wardrobe', 'shaders', 'assets')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $item) -Destination (Join-Path $Prefix 'app') -Recurse
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tools/reservas') -Destination (Join-Path $Prefix 'app/tools/reservas')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tools/deriva-preview.mjs') -Destination (Join-Path $Prefix 'app/tools/deriva-preview.mjs')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tools/deriva-fetch.mjs') -Destination (Join-Path $Prefix 'app/tools/deriva-fetch.mjs')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tools/startup.ps1') -Destination (Join-Path $Prefix 'app/tools/startup.ps1')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tools/software.ps1') -Destination (Join-Path $Prefix 'app/tools/software.ps1')
foreach ($name in @('windows-overview.plm', 'windows-overview.luau')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "tools/$name") -Destination (Join-Path $Prefix "app/tools/$name")
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tools/winget') -Destination (Join-Path $Prefix 'app/tools/winget') -Recurse
foreach ($item in @('desktop.ps1', 'run-desktop.ps1', 'agent-package.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "windows/$item") -Destination (Join-Path $Prefix 'windows')
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'windows/DESKTOP.md') -Destination (Join-Path $Prefix 'README.md')
Invoke-MareaAgentMaintenance $Prefix '--prepare'
$launcherTarget = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$launcherArguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $Prefix 'windows/desktop.ps1') + '" start'
[Marea.Windows.Shortcuts]::Create($shortcutPath, $launcherTarget, $launcherArguments, $Prefix, 'Marea: native Windows desktop companion.', (Join-Path $Prefix 'app/assets/marea.ico'))
& (Join-Path $Prefix 'bin/pleamar.exe') --register-notification-shortcut $shortcutPath
if ($LASTEXITCODE -ne 0) { throw 'Could not register the Marea notification publisher.' }
& (Join-Path $Prefix 'bin/pleamar.exe') --check-notification-shortcut $shortcutPath
if ($LASTEXITCODE -ne 0) { throw 'Could not verify the Marea notification activator.' }
Write-Host "Installed: $Prefix"
Write-Host "Start menu: $shortcutPath"
