param([string]$Screen)
$ErrorActionPreference = 'Stop'
$package = Split-Path $PSScriptRoot -Parent
if (-not $env:PLEAMAR_SOCKET_DIR) { $env:PLEAMAR_SOCKET_DIR = 'marea-desktop' }
if (-not $env:PLEAMAR_WM_NAMESPACE) { $env:PLEAMAR_WM_NAMESPACE = 'marea-desktop' }
if (-not $env:PLEAMAR_MEDIA_NAME) { $env:PLEAMAR_MEDIA_NAME = 'Marea' }
if ($Screen -and $Screen -notmatch '^\\\\\.\\DISPLAY[0-9]+$') { throw 'Use a Windows display name, such as \\.\DISPLAY2.' }
if (-not $env:LANG -or $env:LANG -match '^(C([.].*)?|POSIX)$') {
    $env:LANG = [Globalization.CultureInfo]::CurrentUICulture.Name
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$output = [IO.FileStream]::new((Join-Path $package "logs/marea-$stamp.log"), [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite, 1)
$errors = [IO.FileStream]::new((Join-Path $package "logs/marea-$stamp.error.log"), [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite, 1)
$process = New-Object System.Diagnostics.Process
$wm = New-Object System.Diagnostics.Process
$wmStarted = $false
$wmOutput = $null
$wmErrors = $null
try {
    $process.StartInfo.FileName = Join-Path $package 'bin/pleamar.exe'
    $process.StartInfo.Arguments = '--scene "' + (Join-Path $package 'app/marea-desktop.plm') + '" --no-hud --stall 0'
    if ($Screen) { $process.StartInfo.Arguments += ' --screen "' + $Screen + '"' }
    $process.StartInfo.WorkingDirectory = Join-Path $package 'app'
    $process.StartInfo.EnvironmentVariables['PATH'] = (Join-Path $package 'bin') + ';' + (Join-Path $env:SystemRoot 'System32') + ';' + $env:PATH
    # Hide only the console. STARTUPINFO/SW_HIDE (Start-Process -WindowStyle
    # Hidden) also hides the first Win32 scene window.
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    [void]$process.Start()
    $copyOutput = $process.StandardOutput.BaseStream.CopyToAsync($output)
    $copyErrors = $process.StandardError.BaseStream.CopyToAsync($errors)
    # The native host restores managed windows when this exact engine process
    # exits, even if the PowerShell supervisor is terminated first.
    $wmOutput = [IO.FileStream]::new((Join-Path $package "logs/wm-$stamp.log"), [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite, 1)
    $wmErrors = [IO.FileStream]::new((Join-Path $package "logs/wm-$stamp.error.log"), [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite, 1)
    $wm.StartInfo.FileName = Join-Path $package 'bin/pleamar-wm-host.exe'
    $monitor = if ($Screen) { $Screen } else { 'all' }
    $wm.StartInfo.Arguments = '--monitor "' + $monitor + '" --owner ' + $process.Id
    $wm.StartInfo.WorkingDirectory = Join-Path $package 'app'
    $wm.StartInfo.UseShellExecute = $false
    $wm.StartInfo.CreateNoWindow = $true
    $wm.StartInfo.RedirectStandardOutput = $true
    $wm.StartInfo.RedirectStandardError = $true
    try {
        [void]$wm.Start()
        $wmStarted = $true
        $copyWmOutput = $wm.StandardOutput.BaseStream.CopyToAsync($wmOutput)
        $copyWmErrors = $wm.StandardError.BaseStream.CopyToAsync($wmErrors)
    } catch {
        # Marea remains usable when the optional window manager cannot start.
        $message = [Text.Encoding]::UTF8.GetBytes($_.Exception.Message)
        $wmErrors.Write($message, 0, $message.Length)
    }
    $process.WaitForExit()
    [void]$copyOutput.GetAwaiter().GetResult()
    [void]$copyErrors.GetAwaiter().GetResult()
    $result = $process.ExitCode
    if ($wmStarted) {
        if (-not $wm.WaitForExit(30000)) { throw 'The window manager has not finished restoring windows. Read its log.' }
        [void]$copyWmOutput.GetAwaiter().GetResult()
        [void]$copyWmErrors.GetAwaiter().GetResult()
    }
} finally {
    $wm.Dispose()
    if ($wmOutput) { $wmOutput.Dispose() }
    if ($wmErrors) { $wmErrors.Dispose() }
    $process.Dispose()
    $output.Dispose()
    $errors.Dispose()
}
exit $result
