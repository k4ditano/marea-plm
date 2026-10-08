param([switch]$Library)
$ErrorActionPreference = 'Stop'

function Write-SoftwareRecord($Value) {
    [Console]::WriteLine(($Value | ConvertTo-Json -Depth 8 -Compress))
    [Console]::Out.Flush()
}

function Invoke-MareaSoftware {
    param($Request, [string]$ModulePath = (Join-Path $PSScriptRoot 'winget/Microsoft.WinGet.Client.psd1'))
    if ($Request.action -eq 'cancel') {
        $token = [Guid]::ParseExact([string]$Request.token, 'D').ToString('D')
        $cancel = [Threading.EventWaitHandle]::OpenExisting('Local\Marea.Software.' + $token)
        try { [void]$cancel.Set() } finally { $cancel.Dispose() }
        Write-SoftwareRecord @{type='result'; ok=$true}
        return
    }
    if ($Request.action -notin @('scan','search','install','update')) { throw 'Unknown software action.' }
    if (-not (Test-Path -LiteralPath $ModulePath -PathType Leaf)) {
        throw 'The bundled WinGet client is missing. Reinstall Marea or run windows/prepare-winget.py.'
    }
    $mutating = $Request.action -in @('install','update')
    if ($mutating) {
        if (@($Request.packages).Count -lt 1 -or @($Request.packages).Count -gt 256) { throw 'Select between 1 and 256 packages.' }
        foreach ($package in $Request.packages) {
            if ([string]$package.id -notmatch '^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}$' -or
                [string]$package.version -notmatch '^[^\x00-\x1f]{1,100}$') { throw 'Invalid package identifier or version.' }
        }
    }
    if ($Request.action -eq 'search' -and ([string]$Request.query).Length -notin 2..160) { throw 'Use a query between 2 and 160 characters.' }
    $mutex = $null; $owned = $false; $cancel = $null; $pipeline = $null
    try {
        if ($mutating) {
            $mutex = New-Object Threading.Mutex($false, 'Local\Marea.Software.Install')
            try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
            if (-not $owned) { throw 'Another Marea installation is still running.' }
        }
        $token = [Guid]::NewGuid().ToString('D')
        $cancel = New-Object Threading.EventWaitHandle($false, [Threading.EventResetMode]::ManualReset, ('Local\Marea.Software.' + $token))
        Write-SoftwareRecord @{type='started'; token=$token}
        # The secondary runspace keeps structured results and the progress stream
        # separate. Stop() reaches the module's COM cancellation token.
        $completion = [hashtable]::Synchronized(@{completed=@(); reboot=$false})
        $pipeline = [PowerShell]::Create()
        [void]$pipeline.AddScript({
            param($Request, $ModulePath, $Completion)
            $ErrorActionPreference = 'Stop'
            Import-Module -Name $ModulePath -ErrorAction Stop
            if ($Request.action -eq 'scan') {
                $items = @(Get-WinGetPackage -Source winget | Where-Object { $_.Source -eq 'winget' -and $_.IsUpdateAvailable -and $_.InstalledVersion -and $_.InstalledVersion -ne 'Unknown' } | ForEach-Object {
                    @{id=$_.Id; name=$_.Name; old=$_.InstalledVersion; version=[string]$_.AvailableVersions[0]; source='winget'}
                })
                return @{type='result'; ok=$true; items=$items}
            }
            if ($Request.action -eq 'search') {
                $installed = @{}
                Get-WinGetPackage -Source winget | ForEach-Object { $installed[$_.Id] = $true }
                $items = @(Find-WinGetPackage -Query ([string]$Request.query) -Source winget -Count 12 | ForEach-Object {
                    @{id=$_.Id; name=$_.Name; version=$_.Version; source='winget'; installed=($installed[$_.Id] -eq $true)}
                })
                return @{type='result'; ok=$true; items=$items}
            }
            $completed = @(); $restart = $false
            foreach ($package in $Request.packages) {
                Write-Progress -Id 1000 -Activity $package.name -Status 'Starting' -PercentComplete -1
                $options = @{Id=[string]$package.id; Version=[string]$package.version; Source='winget'; MatchOption='Equals'; Mode='Silent'; ErrorAction='Stop'}
                try {
                    if ($Request.action -eq 'update') { $result = Update-WinGetPackage @options }
                    else { $result = Install-WinGetPackage @options }
                } catch {
                    return @{type='result'; ok=$false; error=$_.Exception.Message;
                        completed=$completed; reboot=$restart}
                }
                $restart = $restart -or $result.RebootRequired
                $Completion.reboot = $restart
                if (-not $result.Succeeded()) {
                    return @{type='result'; ok=$false; error=$result.ErrorMessage(); status=$result.Status;
                        completed=$completed; reboot=$restart}
                }
                $completed += $package.id
                $Completion.completed = $completed
                Write-Progress -Id 1000 -Activity $package.name -Status 'Completed' -Completed
            }
            return @{type='result'; ok=$true; completed=$completed; reboot=$restart}
        }).AddArgument($Request).AddArgument($ModulePath).AddArgument($completion)
        $operation = $pipeline.BeginInvoke()
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $limit = if ($mutating) { 7200 } else { 90 }
        $stopped = $false; $timeout = $false; $last = ''; $item = ''
        while (-not $operation.IsCompleted) {
            # ReadAll bounds retained progress, even during long downloads.
            foreach ($progress in $pipeline.Streams.Progress.ReadAll()) {
                if ($progress.ActivityId -eq 1000) { $item = $progress.Activity }
                $record = @{type='progress'; item=$item; stage=$progress.StatusDescription;
                    percent=$progress.PercentComplete; completed=($progress.RecordType -eq 'Completed')}
                $fingerprint = $record | ConvertTo-Json -Compress
                if ($fingerprint -ne $last) { Write-SoftwareRecord $record; $last = $fingerprint }
            }
            if ($cancel.WaitOne(0) -or $watch.Elapsed.TotalSeconds -gt $limit) {
                $timeout = $watch.Elapsed.TotalSeconds -gt $limit
                $stopped = $true
                $pipeline.Stop()
                break
            }
            Start-Sleep -Milliseconds 100
        }
        if ($stopped) {
            Write-SoftwareRecord @{type='result'; ok=$false; cancelled=(-not $timeout); completed=$completion.completed; reboot=$completion.reboot;
                error=$(if ($timeout) { 'WinGet timed out.' } else { 'Cancellation requested. An installer already applying changes may finish; check updates again.' })}
        } else {
            $results = @($pipeline.EndInvoke($operation))
            $result = $results | Where-Object { $_.type -eq 'result' } | Select-Object -Last 1
            if ($null -eq $result) {
                if ($pipeline.HadErrors) { throw ($pipeline.Streams.Error | Out-String).Trim() }
                throw 'WinGet returned no result.'
            }
            if ($pipeline.HadErrors -and $result.ok) {
                $result.ok = $false
                $result.error = ($pipeline.Streams.Error | Out-String).Trim()
            }
            Write-SoftwareRecord $result
        }
    } finally {
        if ($pipeline) { $pipeline.Dispose() }
        if ($cancel) { $cancel.Dispose() }
        if ($owned) { $mutex.ReleaseMutex() }
        if ($mutex) { $mutex.Dispose() }
    }
}

if (-not $Library) {
    [Console]::InputEncoding = New-Object Text.UTF8Encoding($false)
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
    try {
        $inputText = [Console]::In.ReadToEnd()
        if ($inputText.Length -gt 131072) { throw 'Software request is too large.' }
        Invoke-MareaSoftware ($inputText | ConvertFrom-Json)
    } catch {
        Write-SoftwareRecord @{type='result'; ok=$false; error=$_.Exception.Message}
        exit 1
    }
}
