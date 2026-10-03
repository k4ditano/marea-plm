$ErrorActionPreference = 'Stop'
$package = Split-Path $PSScriptRoot -Parent
$env:PLEAMAR_SOCKET_DIR = 'marea-desktop'
if (-not $env:LANG -or $env:LANG -match '^(C([.].*)?|POSIX)$') {
    $env:LANG = [Globalization.CultureInfo]::CurrentUICulture.Name
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$output = [IO.FileStream]::new((Join-Path $package "logs/marea-$stamp.log"), [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite, 1)
$errors = [IO.FileStream]::new((Join-Path $package "logs/marea-$stamp.error.log"), [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite, 1)
$process = New-Object System.Diagnostics.Process
try {
    $process.StartInfo.FileName = Join-Path $package 'bin/pleamar.exe'
    $process.StartInfo.Arguments = '--scene "' + (Join-Path $package 'app/marea-desktop.plm') + '" --no-hud --stall 0'
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
    $process.WaitForExit()
    [void]$copyOutput.GetAwaiter().GetResult()
    [void]$copyErrors.GetAwaiter().GetResult()
    $result = $process.ExitCode
} finally {
    $process.Dispose()
    $output.Dispose()
    $errors.Dispose()
}
exit $result
