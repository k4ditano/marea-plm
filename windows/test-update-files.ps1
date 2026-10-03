$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'update-files.ps1')
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase ('Marea update Unicode ' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$helper = Join-Path $testRoot 'hold file.ps1'
$source = Join-Path $testRoot 'source.txt'
$destination = Join-Path $testRoot ('destination ' + [char]0x65E5 + [char]0x672C + '.txt')
$ready = Join-Path $testRoot 'ready'
$release = Join-Path $testRoot 'release'
$lockProcess = $null
@'
param([string]$Target, [string]$Ready, [string]$Release, [int]$HoldMilliseconds)
$ErrorActionPreference = 'Stop'
$stream = [IO.File]::Open($Target, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
try {
    [IO.File]::WriteAllText($Ready, 'ready')
    $elapsed = [Diagnostics.Stopwatch]::StartNew()
    while (-not [IO.File]::Exists($Release) -and $elapsed.ElapsedMilliseconds -lt $HoldMilliseconds) {
        Start-Sleep -Milliseconds 20
    }
} finally { $stream.Dispose() }
'@ | Set-Content -LiteralPath $helper -Encoding UTF8

function Start-TestLock([int]$Duration) {
    foreach ($file in @($ready, $release)) {
        if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file }
    }
    $arguments = @('-NoLogo', '-NoProfile', '-File', ('"' + $helper + '"'),
        ('"' + $destination + '"'), ('"' + $ready + '"'), ('"' + $release + '"'), $Duration)
    $script:lockProcess = Start-Process -FilePath powershell.exe -ArgumentList $arguments -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $ready)) {
        if ($lockProcess.HasExited -or [DateTime]::UtcNow -ge $deadline) { throw 'File-lock helper failed to start.' }
        Start-Sleep -Milliseconds 20
    }
}
function Stop-TestLock {
    if ($null -ne $script:lockProcess) {
        [IO.File]::WriteAllText($release, 'release')
        if (-not $script:lockProcess.WaitForExit(6000)) {
            $script:lockProcess.Kill()
            $script:lockProcess.WaitForExit()
            throw 'File-lock helper did not release its handle.'
        }
        $script:lockProcess.Dispose()
        $script:lockProcess = $null
    }
}
try {
    [IO.File]::WriteAllText($source, 'new package contents')
    [IO.File]::WriteAllText($destination, 'old package contents')
    Start-TestLock 1200
    Copy-MareaUpdateFile -Source $source -Destination $destination -TimeoutMilliseconds 4000
    Stop-TestLock
    if ([IO.File]::ReadAllText($destination) -ne 'new package contents') { throw 'Transient-lock replacement failed.' }

    [IO.File]::WriteAllText($destination, 'preserve on timeout')
    Start-TestLock 5000
    $failed = $false
    $elapsed = [Diagnostics.Stopwatch]::StartNew()
    try { Copy-MareaUpdateFile -Source $source -Destination $destination -TimeoutMilliseconds 250 }
    catch { $failed = $true }
    if (-not $failed -or $elapsed.ElapsedMilliseconds -gt 2000) { throw 'Persistent lock was not bounded.' }
    if ([IO.File]::ReadAllText($destination) -ne 'preserve on timeout') { throw 'Locked destination changed.' }
    Stop-TestLock
    Copy-MareaUpdateFile -Source $source -Destination $destination
    if ([IO.File]::ReadAllText($destination) -ne 'new package contents') { throw 'Retry after lock release failed.' }

    $failed = $false
    $elapsed.Restart()
    try { Copy-MareaUpdateFile -Source (Join-Path $testRoot 'missing') -Destination $destination }
    catch { $failed = $true }
    if (-not $failed -or $elapsed.ElapsedMilliseconds -gt 2000) { throw 'An unrelated failure was retried.' }
    if ([IO.File]::ReadAllText($destination) -ne 'new package contents') { throw 'Missing source changed the destination.' }
    Write-Host 'PASS: native transient/persistent file locks, bounded failure, preserved contents, Unicode paths and missing-source failure.'
} finally {
    Stop-TestLock
    $resolved = (Resolve-Path -LiteralPath $testRoot).Path
    if ($resolved -ne [IO.Path]::GetFullPath($testRoot) -or -not $resolved.StartsWith($temporaryBase, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing cleanup outside the owned temporary directory.'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
