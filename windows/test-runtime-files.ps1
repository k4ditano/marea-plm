$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime-files.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('marea-runtime-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$binary = Join-Path $root 'pleamar.exe'
function Expect-Failure([scriptblock]$Action) {
    try { & $Action } catch { return }
    throw 'Expected incomplete or changed runtime to be rejected.'
}
try {
    Set-Content -LiteralPath $binary -Value 'fixture'
    if ((Get-PleamarRuntimeFiles $binary).Count -ne 0) { throw 'Bare binary invented runtime files.' }
    Set-Content -LiteralPath (Join-Path $root 'dxcompiler.dll') -Value 'compiler fixture'
    Expect-Failure { Get-PleamarRuntimeFiles $binary }
    $hashes = [ordered]@{}
    foreach ($relative in @('dxcompiler.dll', 'dxil.dll', 'licenses/dxc/LICENCE-MIT.txt', 'licenses/dxc/LICENSE-LLVM.txt', 'licenses/dxc/LICENSE-MS.txt')) {
        $path = Join-Path $root $relative
        New-Item -ItemType Directory -Force (Split-Path $path -Parent) | Out-Null
        Set-Content -LiteralPath $path -Value ('fixture for ' + $relative)
        $hashes[$relative] = (Get-FileHash -LiteralPath $path).Hash
    }
    $manifest = Join-Path $root 'dxc-runtime.json'
    @{version='test';files=$hashes} | ConvertTo-Json | Set-Content -LiteralPath $manifest -Encoding UTF8
    $files = Get-PleamarRuntimeFiles $binary
    if ($files.Count -ne 6 -or -not $files.Contains('bin/licenses/dxc/LICENSE-MS.txt')) { throw 'Runtime or license files were omitted.' }
    Add-Content -LiteralPath (Join-Path $root 'dxil.dll') -Value 'modified'
    Expect-Failure { Get-PleamarRuntimeFiles $binary }
    $hashes['dxil.dll'] = (Get-FileHash -LiteralPath (Join-Path $root 'dxil.dll')).Hash
    $hashes['../outside.txt'] = $hashes['dxil.dll']
    @{version='test';files=$hashes} | ConvertTo-Json | Set-Content -LiteralPath $manifest -Encoding UTF8
    Expect-Failure { Get-PleamarRuntimeFiles $binary }
    Write-Host 'PASS: bare binary, complete compiler/licenses, missing manifest, modified DLL and arbitrary manifest path.'
} finally {
    $resolvedRoot = [IO.Path]::GetFullPath($root)
    $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $resolvedRoot.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($resolvedRoot) -notmatch '^marea-runtime-test-[0-9a-f]{32}$') { throw 'Invalid runtime test cleanup path.' }
    Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
}
