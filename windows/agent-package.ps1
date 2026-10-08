# Shared by Setup hooks and the source installer; no SDK account is needed.
function Get-MareaAgentFiles([string]$HostBinary, [string]$NodeDirectory) {
    $output = & python (Join-Path $PSScriptRoot 'agent_files.py') --host $HostBinary --node-directory $NodeDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Agent bundle is incomplete. Build its native host and run npm ci in agent first.' }
    $manifest = ($output -join "`n") | ConvertFrom-Json
    $files = [ordered]@{}
    foreach ($item in $manifest.files.PSObject.Properties) { $files[$item.Name] = $item.Value }
    return $files
}

function Test-MareaAgentFiles($Files) {
    $temporary = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) ('marea-agent-bundle-' + [guid]::NewGuid().ToString('N'))))
    $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $temporary.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid agent bundle directory.' }
    New-Item -ItemType Directory -Path $temporary | Out-Null
    try {
        foreach ($relative in $Files.Keys) {
            $target = [IO.Path]::GetFullPath((Join-Path $temporary $relative))
            if (-not $target.StartsWith($temporary + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Agent bundle path escaped its root.' }
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
            [IO.File]::Copy($Files[$relative], $target)
        }
        Test-MareaAgentPackage $temporary
    } finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
}

function New-MareaAgentProcess([string]$Package, [string]$Arguments) {
    $child = New-Object Diagnostics.Process
    $child.StartInfo.FileName = Join-Path $Package 'bin/marea-agent.exe'
    $child.StartInfo.Arguments = $Arguments
    $child.StartInfo.UseShellExecute = $false
    $child.StartInfo.CreateNoWindow = $true
    $child.StartInfo.RedirectStandardInput = $true
    $child.StartInfo.RedirectStandardOutput = $true
    $child.StartInfo.RedirectStandardError = $true
    $child.StartInfo.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
    $child.StartInfo.StandardErrorEncoding = New-Object Text.UTF8Encoding($false)
    $child.StartInfo.WorkingDirectory = $Package
    return $child
}

function Invoke-MareaAgentMaintenance([string]$Package, [string]$Action) {
    if ($Action -notin @('--prepare', '--remove-profile', '--remove-validation-profile')) { throw 'Unknown agent maintenance action.' }
    $child = New-MareaAgentProcess $Package $Action
    try {
        [void]$child.Start()
        $child.StandardInput.Close()
        $output = $child.StandardOutput.ReadToEndAsync()
        $errors = $child.StandardError.ReadToEndAsync()
        if (-not $child.WaitForExit(180000)) { $child.Kill(); $child.WaitForExit(); throw 'Agent preparation timed out.' }
        $text = $output.GetAwaiter().GetResult() + $errors.GetAwaiter().GetResult()
        if ($child.ExitCode -ne 0) { throw "Agent maintenance failed ($($child.ExitCode)): $text" }
    } finally { $child.Dispose() }
}

function Test-MareaAgentPackage([string]$Package) {
    # A separate profile and a new state root keep this check away from an
    # existing chat/account, including when validating an installed package.
    $temporary = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) ('marea-agent-check-' + [guid]::NewGuid().ToString('N'))))
    $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $temporary.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid agent check directory.' }
    New-Item -ItemType Directory -Path $temporary | Out-Null
    $child = New-MareaAgentProcess $Package '--validate-worker'
    $child.StartInfo.EnvironmentVariables['LOCALAPPDATA'] = $temporary
    $started = $false
    try {
        [void]$child.Start()
        $started = $true
        $errors = $child.StandardError.ReadToEndAsync()
        $child.StandardInput.WriteLine('{"type":"start","locale":"en","history":[]}')
        $child.StandardInput.Flush()
        $line = $child.StandardOutput.ReadLineAsync()
        if (-not $line.Wait(180000)) {
            $child.Kill()
            $child.WaitForExit()
            throw ('Packaged AI worker did not become ready: ' + $errors.GetAwaiter().GetResult())
        }
        $value = $line.GetAwaiter().GetResult()
        if (-not $value) {
            if ($child.WaitForExit(5000)) { throw ('Packaged AI worker exited before ready: ' + $errors.GetAwaiter().GetResult()) }
            throw 'Packaged AI worker closed its output before ready.'
        }
        $event = $value | ConvertFrom-Json
        if ($event.type -ne 'ready' -or $event.usable -ne $false -or $event.reason -ne 'signed_out') {
            throw "Unexpected AI worker response in an empty account: $value"
        }
        $child.StandardInput.WriteLine('{"type":"shutdown"}')
        $child.StandardInput.Close()
        if (-not $child.WaitForExit(10000)) { throw 'Packaged AI worker did not shut down.' }
        if ($child.ExitCode -ne 0) { throw ('Packaged AI worker failed: ' + $errors.GetAwaiter().GetResult()) }
    } finally {
        if ($started -and -not $child.HasExited) { $child.Kill(); $child.WaitForExit() }
        $child.Dispose()
        try { Invoke-MareaAgentMaintenance $Package '--remove-validation-profile' }
        finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
    }
}
