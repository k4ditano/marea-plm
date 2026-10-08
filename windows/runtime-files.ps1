function Get-PleamarRuntimeFiles([string]$PleamarBinary) {
    $directory = Split-Path $PleamarBinary -Parent
    $files = [ordered]@{}
    $manifest = Join-Path $directory 'dxc-runtime.json'
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        foreach ($dll in @('dxcompiler.dll', 'dxil.dll')) {
            if (Test-Path -LiteralPath (Join-Path $directory $dll)) { throw 'Incomplete DXC package: dxc-runtime.json is missing.' }
        }
        Write-Warning 'No app-local DXC package; the system shader compiler may make startup slower.'
        return $files
    }
    $data = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    # A manifest from a runtime package can describe only these known files,
    # never arbitrary destinations outside the installation.
    $required = @('dxcompiler.dll', 'dxil.dll', 'licenses/dxc/LICENCE-MIT.txt', 'licenses/dxc/LICENSE-LLVM.txt', 'licenses/dxc/LICENSE-MS.txt')
    if (-not $data.version -or -not $data.files -or @($data.files.PSObject.Properties).Count -ne $required.Count) {
        throw 'Incomplete DXC package manifest.'
    }
    foreach ($relative in $required) {
        $source = Join-Path $directory $relative
        $expected = $data.files.PSObject.Properties[$relative]
        if (-not $expected -or $expected.Value -notmatch '^[0-9a-fA-F]{64}$' -or
            -not (Test-Path -LiteralPath $source -PathType Leaf) -or
            (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expected.Value) {
            throw "Incomplete or changed DXC package file: $relative"
        }
        $files[('bin/' + $relative)] = $source
    }
    $files['bin/dxc-runtime.json'] = $manifest
    return $files
}
