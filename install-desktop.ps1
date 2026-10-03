param(
    [string]$PleamarBinary = (Join-Path $PSScriptRoot '../pleamar/target/release/pleamar.exe'),
    [string]$DerivaWorkerBinary = (Join-Path $PSScriptRoot 'deriva/target/release/deriva-worker.exe'),
    [string]$Prefix = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Marea Windows')
)
$ErrorActionPreference = 'Stop'
$PleamarBinary = (Resolve-Path -LiteralPath $PleamarBinary).Path
. (Join-Path $PSScriptRoot 'windows/runtime-files.ps1')
$runtimeFiles = Get-PleamarRuntimeFiles $PleamarBinary
$Prefix = [IO.Path]::GetFullPath($Prefix)
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'Marea Windows.lnk'
# Detect an incomplete source package before creating an installation folder.
foreach ($relative in @('marea.plm', 'marea.luau', 'LICENSE', 'common', 'lang', 'wardrobe', 'shaders', 'assets', 'assets/marea.ico', 'tools/reservas', 'windows/desktop.ps1', 'windows/run-desktop.ps1', 'windows/shortcuts.ps1', 'windows/runtime_probe.py', 'windows/DESKTOP.md')) {
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
& $PleamarBinary --check (Join-Path $PSScriptRoot 'marea-desktop.plm')
if ($LASTEXITCODE -ne 0) { throw 'The desktop profile did not compile.' }
foreach ($folder in @('app', 'app/tools', 'bin', 'windows', 'logs')) {
    New-Item -ItemType Directory -Force (Join-Path $Prefix $folder) | Out-Null
}
Copy-Item -LiteralPath $PleamarBinary -Destination (Join-Path $Prefix 'bin/pleamar.exe')
Copy-Item -LiteralPath $DerivaWorkerBinary -Destination (Join-Path $Prefix 'bin/deriva-worker.exe')
foreach ($relative in $runtimeFiles.Keys) {
    $destination = Join-Path $Prefix $relative
    New-Item -ItemType Directory -Force (Split-Path $destination -Parent) | Out-Null
    Copy-Item -LiteralPath $runtimeFiles[$relative] -Destination $destination
}
foreach ($item in @('marea.plm', 'marea.luau', 'marea-desktop.plm', 'marea-desktop.luau', 'LICENSE', 'common', 'lang', 'wardrobe', 'shaders', 'assets')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $item) -Destination (Join-Path $Prefix 'app') -Recurse
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tools/reservas') -Destination (Join-Path $Prefix 'app/tools/reservas')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tools/deriva-preview.mjs') -Destination (Join-Path $Prefix 'app/tools/deriva-preview.mjs')
foreach ($item in @('desktop.ps1', 'run-desktop.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "windows/$item") -Destination (Join-Path $Prefix 'windows')
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'windows/DESKTOP.md') -Destination (Join-Path $Prefix 'README.md')
$launcherTarget = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$launcherArguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $Prefix 'windows/desktop.ps1') + '" start'
[Marea.Windows.Shortcuts]::Create($shortcutPath, $launcherTarget, $launcherArguments, $Prefix, 'Marea: native Windows desktop companion.', (Join-Path $Prefix 'app/assets/marea.ico'))
& (Join-Path $Prefix 'bin/pleamar.exe') --register-notification-shortcut $shortcutPath
if ($LASTEXITCODE -ne 0) { throw 'Could not register the Marea notification publisher.' }
Write-Host "Installed: $Prefix"
Write-Host "Start menu: $shortcutPath"
