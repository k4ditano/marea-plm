param([string]$Action = 'start', [int]$Seconds = 30, [string]$Out, [string]$Screen)
$ErrorActionPreference = 'Stop'
$package = Split-Path $PSScriptRoot -Parent
$binary = Join-Path $package 'bin/pleamar.exe'
$scene = Join-Path $package 'app/marea-desktop.plm'
$stateFolder = Join-Path $package 'logs'
$env:PLEAMAR_SOCKET_DIR = 'marea-desktop'
if (-not (Test-Path -LiteralPath $binary)) { throw "Native pleamar executable missing: $binary" }

function Test-MareaRunning {
    # Native stderr can throw NativeCommandError under Windows PowerShell 5.1.
    # A missing pipe is expected before launch, and must not abort startup.
    try {
        & $binary --say marea-desktop 'get open' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Test-MareaInitialized {
    try {
        $value = & $binary --say marea-desktop 'get windows_initialized' 2>$null
        return $LASTEXITCODE -eq 0 -and ($value -join '').Trim() -eq 'true'
    } catch { return $false }
}

switch ($Action) {
    'report' {
        $reportArgs = @('--report', '--seconds', [string]$Seconds)
        if ($Out) { $reportArgs += @('--out', $Out) }
        & $binary @reportArgs
        exit $LASTEXITCODE
    }
    'start' {
        if (Test-MareaRunning) {
            if (-not (Test-MareaInitialized)) { throw "Marea is running but its logic is not ready. Read $stateFolder" }
            Write-Host 'Marea is already running.'; exit 0
        }
        New-Item -ItemType Directory -Force $stateFolder | Out-Null
        $hostBinary = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
        $runner = Join-Path $PSScriptRoot 'run-desktop.ps1'
        $runnerArgs = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $runner + '"'))
        if ($Screen) {
            if ($Screen -notmatch '^\\\\\.\\DISPLAY[0-9]+$') { throw 'Use a Windows display name, such as \\.\DISPLAY2.' }
            $runnerArgs += @('-Screen', ('"' + $Screen + '"'))
        }
        $process = Start-Process -FilePath $hostBinary -ArgumentList $runnerArgs -WorkingDirectory $package -WindowStyle Hidden -PassThru
        $deadline = [DateTime]::UtcNow.AddSeconds(20)
        while (-not (Test-MareaInitialized)) {
            if ($process.HasExited) { throw "Marea exited with code $($process.ExitCode). Read $stateFolder" }
            if ([DateTime]::UtcNow -gt $deadline) { throw "Marea did not become ready within 20 seconds. Read $stateFolder" }
            Start-Sleep -Milliseconds 300
        }
        Write-Host "Marea Windows started. Logs: $stateFolder"
        exit 0
    }
    'stop' {
        if (Test-MareaRunning) {
            & $binary --say marea-desktop quit
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        $deadline = [DateTime]::UtcNow.AddSeconds(15)
        while (Test-MareaRunning) {
            if ([DateTime]::UtcNow -gt $deadline) { throw 'Marea has not finished closing.' }
            Start-Sleep -Milliseconds 200
        }
        # The IPC listener closes before GPU/service shutdown finishes. The
        # image remains locked until the owning process actually exits.
        foreach ($owner in [Diagnostics.Process]::GetProcessesByName('pleamar')) {
            try {
                $belongs = $false
                try { $belongs = $owner.MainModule.FileName -eq $binary } catch {}
                if ($belongs -and -not $owner.WaitForExit(15000)) { throw "Marea's process $($owner.Id) has not finished closing." }
            } finally { $owner.Dispose() }
        }
        foreach ($owner in [Diagnostics.Process]::GetProcessesByName('pleamar-wm-host')) {
            try {
                $belongs = $false
                try { $belongs = $owner.MainModule.FileName -eq (Join-Path $package 'bin/pleamar-wm-host.exe') } catch {}
                if ($belongs -and -not $owner.WaitForExit(30000)) { throw 'The window manager is still restoring windows.' }
            } finally { $owner.Dispose() }
        }
        Write-Host 'Marea stopped.'
        exit 0
    }
    'status' {
        if (Test-MareaRunning) {
            if (-not (Test-MareaInitialized)) { Write-Host 'Marea is running but its logic is not ready.'; exit 2 }
            Write-Host 'Marea is running.'; exit 0
        }
        Write-Host 'Marea is not running.'; exit 1
    }
    default {
        if ($Action -notin @('celebrate', 'rage', 'settings', 'customize', 'search', 'calendar', 'show_walls', 'shot_region', 'shot_screen', 'shot_window', 'record_toggle')) {
            throw 'Supported actions: start, stop, status, report [-Seconds N] [-Out FILE], celebrate, rage, settings, customize, search, calendar, show_walls, shot_region, shot_screen, shot_window, record_toggle.'
        }
        & $binary --say marea-desktop "emit $Action"
        exit $LASTEXITCODE
    }
}
