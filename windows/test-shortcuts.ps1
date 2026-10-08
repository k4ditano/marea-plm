param([string]$PleamarBinary)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'shortcuts.ps1')
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$unicode = [string][char]0x00f1 + ' ' + [char]0x6d77 + ' ' + [char]::ConvertFromUtf32(0x1f680)
$fixture = Join-Path $temporaryRoot ('marea shortcut ' + $unicode + ' ' + [Guid]::NewGuid().ToString('N'))
$resolvedFixture = [IO.Path]::GetFullPath($fixture)
if (-not $resolvedFixture.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid fixture path.' }
New-Item -ItemType Directory -Path $fixture | Out-Null
$fixtureBinary = $null
try {
    $link = Join-Path $fixture 'Marea test.lnk'
    $target = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $arguments = '-NoProfile -File "' + (Join-Path $fixture ('script ' + $unicode + '.ps1')) + '" start'
    $description = 'Marea ' + $unicode
    $icon = Join-Path $fixture ('Marea ' + $unicode + '.ico')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../assets/marea.ico') -Destination $icon
    [Marea.Windows.Shortcuts]::Create($link, $target, $arguments, $fixture, $description, $icon)
    function Assert-Shortcut {
        $value = [Marea.Windows.Shortcuts]::Read($link)
        if ($value.Target -ne $target -or $value.Arguments -cne $arguments -or $value.WorkingDirectory -ne $fixture -or $value.Description -cne $description -or $value.Icon -cne $icon -or $value.IconIndex -ne 0) {
            throw ('Shortcut lost Unicode or metadata: ' + ($value | ConvertTo-Json -Compress))
        }
    }
    Assert-Shortcut
    $original = (Get-FileHash -LiteralPath $link -Algorithm SHA256).Hash
    $rejected = $false
    try { [Marea.Windows.Shortcuts]::Create($link, $target, 'changed', $fixture, 'changed') } catch { $rejected = $true }
    if (-not $rejected -or (Get-FileHash -LiteralPath $link -Algorithm SHA256).Hash -ne $original) { throw 'An existing shortcut was overwritten.' }
    # Updating an older installation must keep its launch metadata intact.
    $icon = Join-Path $fixture ('Updated ' + $unicode + '.ico')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../assets/marea.ico') -Destination $icon
    [Marea.Windows.Shortcuts]::SetIcon($link, $icon)
    Assert-Shortcut
    if ($PleamarBinary) {
        # The publisher's registry identity belongs to this fresh fixture path.
        $fixtureBinary = Join-Path $fixture 'pleamar.exe'
        Copy-Item -LiteralPath $PleamarBinary -Destination $fixtureBinary
        $broker = Join-Path (Split-Path $PleamarBinary -Parent) 'pleamar-notifications.exe'
        if (Test-Path -LiteralPath $broker) { Copy-Item -LiteralPath $broker -Destination $fixture }
        & $fixtureBinary --register-notification-shortcut $link
        if ($LASTEXITCODE -ne 0) { throw 'Native notification registration failed.' }
        Assert-Shortcut
    }
    Write-Host 'PASS: native Unicode shortcut fields, icon creation/update, no overwrite and optional publisher roundtrip'
} finally {
    # This directory was exclusively created by this test below the checked temp root.
    if ($fixtureBinary) {
        & $fixtureBinary --unregister-notification-publisher
        if ($LASTEXITCODE -ne 0) { throw 'Could not remove the fixture notification registration.' }
    }
    if ([IO.Path]::GetFullPath($fixture) -ne $resolvedFixture) { throw 'Fixture path changed.' }
    Remove-Item -LiteralPath $resolvedFixture -Recurse -Force
}
