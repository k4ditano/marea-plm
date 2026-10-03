param(
    [string]$PleamarBinary = (Join-Path $PSScriptRoot '../pleamar/target/release/pleamar.exe'),
    [string]$DerivaWorkerBinary = (Join-Path $PSScriptRoot 'deriva/target/release/deriva-worker.exe'),
    [string]$Prefix = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Marea Windows'),
    [switch]$NoStart
)
$ErrorActionPreference = 'Stop'
$PleamarBinary = (Resolve-Path -LiteralPath $PleamarBinary).Path
. (Join-Path $PSScriptRoot 'windows/runtime-files.ps1')
. (Join-Path $PSScriptRoot 'windows/update-files.ps1')
$runtimeFiles = Get-PleamarRuntimeFiles $PleamarBinary
$Prefix = (Resolve-Path -LiteralPath $Prefix).Path
$entry = Join-Path $Prefix 'windows/desktop.ps1'
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'Marea Windows.lnk'
if (-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) { throw "Marea's Start menu shortcut is missing: $shortcutPath" }
. (Join-Path $PSScriptRoot 'windows/shortcuts.ps1')
$shortcut = [Marea.Windows.Shortcuts]::Read($shortcutPath)
if ($shortcut.Arguments.IndexOf(('"' + $entry + '"'), [StringComparison]::OrdinalIgnoreCase) -lt 0) {
    throw 'The existing Marea shortcut belongs to another installation; it was not changed.'
}
foreach ($required in @('app/marea-desktop.plm', 'app/marea-desktop.luau', 'bin/pleamar.exe', 'windows/desktop.ps1')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Prefix $required))) { throw "Not a Marea desktop installation: $Prefix" }
}
python (Join-Path $PSScriptRoot 'windows/runtime_probe.py') --binary $PleamarBinary
if ($LASTEXITCODE -ne 0) { throw 'The native pleamar runtime check failed; the installed Marea was not stopped.' }
$DerivaWorkerBinary = (Resolve-Path -LiteralPath $DerivaWorkerBinary).Path
python (Join-Path $PSScriptRoot 'windows/test-deriva-native.py') --worker $DerivaWorkerBinary
if ($LASTEXITCODE -ne 0) { throw 'The Deriva worker failed its isolated library check; the installed Marea was not stopped.' }
python (Join-Path $PSScriptRoot 'windows/build-desktop.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not generate the desktop profile.' }
& $PleamarBinary --check (Join-Path $PSScriptRoot 'marea-desktop.plm')
if ($LASTEXITCODE -ne 0) { throw 'The new scene did not compile.' }
$files = [ordered]@{
    'bin/pleamar.exe' = $PleamarBinary
    'bin/deriva-worker.exe' = $DerivaWorkerBinary
    'app/marea-desktop.plm' = (Join-Path $PSScriptRoot 'marea-desktop.plm')
    'app/marea-desktop.luau' = (Join-Path $PSScriptRoot 'marea-desktop.luau')
    'app/tools/reservas' = (Join-Path $PSScriptRoot 'tools/reservas')
    'app/tools/deriva-preview.mjs' = (Join-Path $PSScriptRoot 'tools/deriva-preview.mjs')
    'windows/desktop.ps1' = (Join-Path $PSScriptRoot 'windows/desktop.ps1')
    'windows/run-desktop.ps1' = (Join-Path $PSScriptRoot 'windows/run-desktop.ps1')
    'README.md' = (Join-Path $PSScriptRoot 'windows/DESKTOP.md')
}
# An upstream scene can add a shader, translation or asset. Updating only the
# two generated files leaves an installation with incompatible resources.
foreach ($relative in $runtimeFiles.Keys) { $files[$relative] = $runtimeFiles[$relative] }
foreach ($relative in @('marea.plm', 'marea.luau', 'LICENSE')) {
    $files[('app/' + $relative)] = Join-Path $PSScriptRoot $relative
}
foreach ($folder in @('common', 'lang', 'wardrobe', 'shaders', 'assets')) {
    $sourceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot $folder)).Path
    foreach ($source in Get-ChildItem -LiteralPath $sourceRoot -Recurse -File) {
        $relative = $source.FullName.Substring($sourceRoot.Length + 1).Replace('\', '/')
        $files[('app/' + $folder + '/' + $relative)] = $source.FullName
    }
}
foreach ($source in $files.Values) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing packaged input: $source" }
}
# Compute metadata before stopping the working installation. Use the framework
# directly so launchers with a different PSModulePath cannot hide Get-FileHash.
$hashStream = [IO.File]::OpenRead($PleamarBinary)
$hasher = [Security.Cryptography.SHA256]::Create()
try { $executableHash = [BitConverter]::ToString($hasher.ComputeHash($hashStream)).Replace('-', '') }
finally { $hashStream.Dispose(); $hasher.Dispose() }
$runtimeHashes = [ordered]@{}
$runtimeHashes['bin/deriva-worker.exe'] = (Get-FileHash -LiteralPath $DerivaWorkerBinary -Algorithm SHA256).Hash.ToLowerInvariant()
foreach ($relative in $runtimeFiles.Keys) {
    $runtimeHashes[$relative] = (Get-FileHash -LiteralPath $runtimeFiles[$relative] -Algorithm SHA256).Hash.ToLowerInvariant()
}
$backup = Join-Path $Prefix ('backups/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Force $backup | Out-Null
Copy-Item -LiteralPath $shortcutPath -Destination (Join-Path $backup 'Marea Windows.lnk')
# Stop the owning process before replacing its executable. The calendar and
# preferences live outside this package and are never part of an update.
& powershell.exe -NoLogo -NoProfile -File $entry stop
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the installed Marea.' }
# Older installed launchers only waited for the pipe to close. Also wait here
# so an upgrade from those packages cannot overwrite a still-mapped executable.
$installedBinary = Join-Path $Prefix 'bin/pleamar.exe'
foreach ($owner in [Diagnostics.Process]::GetProcessesByName('pleamar')) {
    try {
        $belongs = $false
        try { $belongs = $owner.MainModule.FileName -eq $installedBinary } catch {}
        if ($belongs -and -not $owner.WaitForExit(15000)) { throw "The installed executable is still in use by process $($owner.Id)." }
    } finally { $owner.Dispose() }
}
$newFiles = @()
foreach ($relative in @($files.Keys) + @('build-info.json')) {
    $saved = Join-Path $backup $relative
    $previous = Join-Path $Prefix $relative
    if (Test-Path -LiteralPath $previous -PathType Leaf) {
        New-Item -ItemType Directory -Force (Split-Path $saved -Parent) | Out-Null
        Copy-Item -LiteralPath $previous -Destination $saved
    } else { $newFiles += $relative }
}
try {
    foreach ($relative in $files.Keys) {
        $destination = Join-Path $Prefix $relative
        New-Item -ItemType Directory -Force (Split-Path $destination -Parent) | Out-Null
        Copy-MareaUpdateFile -Source $files[$relative] -Destination $destination
    }
    [Marea.Windows.Shortcuts]::SetIcon($shortcutPath, (Join-Path $Prefix 'app/assets/marea.ico'))
    & (Join-Path $Prefix 'bin/pleamar.exe') --register-notification-shortcut $shortcutPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not register the updated Marea notification publisher.' }
    # Old test counts describe the previous executable. Keep them in its
    # backup, never label a newly installed binary with stale test results.
    [ordered]@{
        InstalledAt = [DateTime]::UtcNow.ToString('o')
        ExecutableSHA256 = $executableHash
        UpdatedRuntimeFiles = $runtimeHashes
        Profile = 'marea-desktop'
        Backup = $backup
        LaunchDeferred = [bool]$NoStart
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Prefix 'build-info.json') -Encoding UTF8
    if (-not $NoStart) {
        & powershell.exe -NoLogo -NoProfile -File $entry start
        if ($LASTEXITCODE -ne 0) { throw 'The updated Marea failed to start.' }
    }
} catch {
    $failure = $_
    & powershell.exe -NoLogo -NoProfile -File $entry stop
    foreach ($relative in @($files.Keys) + @('build-info.json')) {
        $saved = Join-Path $backup $relative
        $destination = Join-Path $Prefix $relative
        if (Test-Path -LiteralPath $saved -PathType Leaf) {
            Copy-MareaUpdateFile -Source $saved -Destination $destination
        } elseif ($newFiles -contains $relative) {
            if (Test-Path -LiteralPath $destination -PathType Leaf) { Remove-Item -LiteralPath $destination }
        }
    }
    Copy-Item -LiteralPath (Join-Path $backup 'Marea Windows.lnk') -Destination $shortcutPath -Force
    if (-not $NoStart) { & powershell.exe -NoLogo -NoProfile -File $entry start }
    throw $failure
}
Write-Host "Updated: $Prefix"
Write-Host "Previous package files preserved: $backup"
