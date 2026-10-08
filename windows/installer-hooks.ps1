param(
    [ValidateSet('validate', 'prepare', 'stop', 'register', 'unregister')][string]$Action = 'validate',
    [Parameter(Mandatory = $true)][string]$Package,
    [string]$Target,
    [string]$Shortcut,
    [string]$ResultFile
)
$ErrorActionPreference = 'Stop'
$identity = 'A8D741A8-45D5-4DE8-A38E-27DA65D253F8'
. (Join-Path $PSScriptRoot 'agent-package.ps1')

function Get-PackageHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose(); $stream.Dispose() }
}

function Invoke-PackageProcess([string]$Executable, [string]$Arguments, [int]$Timeout = 30000) {
    $child = New-Object Diagnostics.Process
    try {
        $child.StartInfo.FileName = $Executable
        $child.StartInfo.Arguments = $Arguments
        $child.StartInfo.UseShellExecute = $false
        $child.StartInfo.CreateNoWindow = $true
        $child.StartInfo.RedirectStandardOutput = $true
        $child.StartInfo.RedirectStandardError = $true
        $child.StartInfo.WorkingDirectory = $Package
        $child.StartInfo.EnvironmentVariables['PATH'] = (Join-Path $Package 'bin') + ';' + (Join-Path $env:SystemRoot 'System32')
        [void]$child.Start()
        $output = $child.StandardOutput.ReadToEndAsync()
        $errors = $child.StandardError.ReadToEndAsync()
        if (-not $child.WaitForExit($Timeout)) { $child.Kill(); $child.WaitForExit(); throw 'Package validation timed out.' }
        $text = $output.GetAwaiter().GetResult() + $errors.GetAwaiter().GetResult()
        if ($child.ExitCode -ne 0) { throw "Package command failed ($($child.ExitCode)): $text" }
        return $text
    } finally { $child.Dispose() }
}

function Stop-OwnedMarea([string]$Directory) {
    $binary = Join-Path $Directory 'bin/pleamar.exe'
    $owners = @()
    foreach ($process in [Diagnostics.Process]::GetProcessesByName('pleamar')) {
        $belongs = $false
        try { $belongs = $process.MainModule.FileName -eq $binary } catch {}
        if ($belongs) { $owners += $process } else { $process.Dispose() }
    }
    try {
        if ($owners.Count -gt 0) {
            $env:PLEAMAR_SOCKET_DIR = 'marea-desktop'
            $null = Invoke-PackageProcess $binary '--say marea-desktop quit' 10000
        }
        foreach ($process in $owners) {
            if (-not $process.WaitForExit(15000)) { throw 'Marea is still closing. Close it and retry.' }
        }
    } finally { foreach ($process in $owners) { $process.Dispose() } }
    # Owner-exit recovery may outlive the engine. Never replace its executable
    # until the exact host from this installation has restored its windows.
    foreach ($process in [Diagnostics.Process]::GetProcessesByName('pleamar-wm-host')) {
        try {
            $belongs = $false
            try { $belongs = $process.MainModule.FileName -eq (Join-Path $Directory 'bin/pleamar-wm-host.exe') } catch {}
            if ($belongs -and -not $process.WaitForExit(30000)) { throw 'The window manager is still restoring windows. Close it and retry.' }
        } finally { $process.Dispose() }
    }
    foreach ($process in [Diagnostics.Process]::GetProcessesByName('pleamar-notifications')) {
        try {
            $belongs = $false
            try { $belongs = $process.MainModule.FileName -eq (Join-Path $Directory 'bin/pleamar-notifications.exe') } catch {}
            if ($belongs -and -not $process.WaitForExit(20000)) { throw 'The notification activator is still closing. Retry the update.' }
        } finally { $process.Dispose() }
    }
}

function Test-Package {
    $manifest = Get-Content -LiteralPath (Join-Path $Package 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.app_id -ne $identity -or $manifest.architecture -ne 'x86_64') { throw 'Wrong package identity or architecture.' }
    $prefix = $Package.TrimEnd('\') + '\'
    foreach ($file in $manifest.files.PSObject.Properties) {
        $path = [IO.Path]::GetFullPath((Join-Path $Package $file.Name))
        if (-not $path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or
            $file.Value -notmatch '^[0-9a-f]{64}$' -or -not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-PackageHash $path) -ne $file.Value) {
            throw "Incomplete or changed package file: $($file.Name)"
        }
    }
    foreach ($required in @('bin/pleamar.exe','bin/pleamar-notifications.exe','bin/pleamar-wm.exe','bin/pleamar-wm-host.exe','bin/licenses/pleamar-wm/LICENSE','bin/deriva-worker.exe','bin/node.exe','bin/marea-agent.exe','bin/dxcompiler.dll','bin/dxil.dll',
        'app/agent/worker.mjs','app/agent/package-lock.json','app/agent/node_modules/@earendil-works/pi-coding-agent/package.json','windows/agent-package.ps1',
        'bin/vcruntime140.dll','bin/vcruntime140_1.dll','bin/msvcp140.dll','app/marea-desktop.plm','app/marea-desktop.luau','app/assets/marea.ico','app/tools/deriva-preview.mjs','app/tools/deriva-fetch.mjs','app/tools/startup.ps1','app/tools/software.ps1','app/tools/winget/Microsoft.WinGet.Client.psd1')) {
        if (-not $manifest.files.PSObject.Properties[$required]) { throw "Missing package manifest entry: $required" }
    }
    if ($manifest.wm_source -notmatch '^[0-9a-f]{40}$') { throw 'Missing window manager source revision.' }
    # Real execution checks both the loader dependencies and default Luau. It
    # uses an absent output and an isolated library, never the user's desktop.
    $temporary = Join-Path ([IO.Path]::GetTempPath()) ('marea-setup-' + [guid]::NewGuid().ToString('N'))
    $temporary = [IO.Path]::GetFullPath($temporary)
    $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $temporary.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid temporary root.' }
    New-Item -ItemType Directory -Path $temporary | Out-Null
    $names = @('APPDATA','LOCALAPPDATA','MAREA_DERIVA_DIR','PLEAMAR_CONFIG','PLEAMAR_WM_CONFIG','PLEAMAR_SOCKET_DIR','PLEAMAR_WM_NAMESPACE','PLEAMAR_NO_RELAUNCH')
    $previous = @{}
    foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    try {
        $env:APPDATA = Join-Path $temporary 'roaming'
        $env:LOCALAPPDATA = Join-Path $temporary 'local'
        $env:MAREA_DERIVA_DIR = Join-Path $temporary 'library'
        $env:PLEAMAR_CONFIG = Join-Path $temporary 'config'
        $env:PLEAMAR_WM_CONFIG = Join-Path $temporary 'empty-session.conf'
        [IO.File]::WriteAllText($env:PLEAMAR_WM_CONFIG, '')
        $env:PLEAMAR_SOCKET_DIR = 'marea-setup-' + [guid]::NewGuid().ToString('N')
        $env:PLEAMAR_WM_NAMESPACE = $env:PLEAMAR_SOCKET_DIR
        $env:PLEAMAR_NO_RELAUNCH = '1'
        $scene = Join-Path $temporary 'probe.plm'
        $marker = 'MAREA_SETUP_LUAU_' + [guid]::NewGuid().ToString('N')
        [IO.File]::WriteAllText($scene, 'scene Probe { surface { kind: window; size: 40, 40 } fact ready = false }')
        [IO.File]::WriteAllText((Join-Path $temporary 'probe.luau'), ('assert(type(sys.watch) == "function"); fact.ready = true; log("' + $marker + '")'))
        $trace = Invoke-PackageProcess (Join-Path $Package 'bin/pleamar.exe') ('--scene "' + $scene + '" --screen marea-setup-absent --no-hud --stall 0 --seconds 2')
        if (-not $trace.Contains($marker) -or $trace.Contains('first frame')) { throw 'Native Luau preflight failed.' }
        $null = Invoke-PackageProcess (Join-Path $Package 'bin/pleamar.exe') ('--check "' + (Join-Path $Package 'app/marea-desktop.plm') + '"')
        $null = Invoke-PackageProcess (Join-Path $Package 'bin/deriva-worker.exe') 'stats'
        $caps = Invoke-PackageProcess (Join-Path $Package 'bin/pleamar-wm.exe') 'capabilities' | ConvertFrom-Json
        if ($caps.platform -ne 'windows' -or !$caps.explicit_layouts) { throw 'Native window manager capability query failed.' }
        # A fresh, isolated session starts free and never changes window geometry.
        $wm = Invoke-PackageProcess (Join-Path $Package 'bin/pleamar-wm-host.exe') '--monitor all --seconds 1' | ConvertFrom-Json
        if (!$wm.stopped -or $wm.pending_recovery -ne 0) { throw 'Native window manager preflight failed.' }
        $node = Invoke-PackageProcess (Join-Path $Package 'bin/node.exe') '--version'
        if ($node.Trim() -ne $manifest.node_version) { throw 'Unexpected packaged Node.js version.' }
        Test-MareaAgentPackage $Package
    } finally {
        foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
        # Only this freshly created, resolved temporary directory is removed.
        Remove-Item -LiteralPath $temporary -Recurse -Force
    }
}

try {
    $Package = [IO.Path]::GetFullPath($Package)
    switch ($Action) {
        'validate' { Test-Package }
        'prepare' {
            Test-Package
            $Target = [IO.Path]::GetFullPath($Target)
            if (Test-Path -LiteralPath $Target) {
                if (-not (Test-Path -LiteralPath (Join-Path $Target 'package.json'))) {
                    if (@(Get-ChildItem -LiteralPath $Target -Force).Count -ne 0) { throw 'Choose an empty folder or an existing Marea Setup installation. Source-script installations are preserved separately.' }
                } else {
                    $old = Get-Content -LiteralPath (Join-Path $Target 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($old.app_id -ne $identity) { throw 'The target belongs to another package.' }
                    Stop-OwnedMarea $Target
                    # Fail before replacing any file if another process holds it.
                    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $Target 'bin') -File) {
                        $lock = [IO.File]::Open($file.FullName, 'Open', 'ReadWrite', 'None')
                        $lock.Dispose()
                    }
                }
            }
        }
        'stop' { Stop-OwnedMarea $Package }
        'unregister' {
            $null = Invoke-PackageProcess (Join-Path $Package 'bin/pleamar.exe') '--unregister-notification-publisher'
            . (Join-Path $Package 'app/tools/startup.ps1') -Library
            $null = Invoke-MareaStartup -Package $Package -Action disable
            Invoke-MareaAgentMaintenance $Package '--remove-profile'
            Invoke-MareaAgentMaintenance $Package '--remove-validation-profile'
        }
        'register' {
            Invoke-MareaAgentMaintenance $Package '--prepare'
            $null = Invoke-PackageProcess (Join-Path $Package 'bin/pleamar.exe') ('--register-notification-shortcut "' + $Shortcut + '"')
            $null = Invoke-PackageProcess (Join-Path $Package 'bin/pleamar.exe') ('--check-notification-shortcut "' + $Shortcut + '"')
        }
    }
    if ($ResultFile) { [IO.File]::WriteAllText($ResultFile, 'OK') }
    Write-Output 'PASS: native package checks completed without a display.'
    exit 0
} catch {
    if ($ResultFile) { [IO.File]::WriteAllText($ResultFile, $_.Exception.Message) }
    Write-Error $_ -ErrorAction Continue
    exit 1
}
