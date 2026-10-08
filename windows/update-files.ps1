function Copy-MareaUpdateFile {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$Destination,
        [ValidateRange(0, 30000)][int]$TimeoutMilliseconds = 10000
    )
    $elapsed = [Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        try {
            Copy-Item -LiteralPath $Source -Destination $Destination -Force -ErrorAction Stop
            return
        } catch {
            # An exited image can remain briefly locked by another component.
            # Retry only sharing/lock violations; permissions and missing files
            # must fail immediately, and another process is never terminated.
            $sharingViolation = $false
            $exception = $_.Exception
            while ($null -ne $exception) {
                if (($exception.HResult -band 65535) -in @(32, 33)) { $sharingViolation = $true }
                $exception = $exception.InnerException
            }
            if (-not $sharingViolation -or $elapsed.ElapsedMilliseconds -ge $TimeoutMilliseconds) { throw }
            $remaining = [Math]::Max(0, $TimeoutMilliseconds - $elapsed.ElapsedMilliseconds)
            Start-Sleep -Milliseconds ([Math]::Min(200, $remaining))
        }
    }
}
