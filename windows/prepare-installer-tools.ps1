param([string]$Directory = (Join-Path $PSScriptRoot '../.tools/installer-tools'))
$ErrorActionPreference = 'Stop'
$Directory = [IO.Path]::GetFullPath($Directory)
New-Item -ItemType Directory -Force -Path $Directory | Out-Null
function Get-Pinned([string]$Url, [string]$Name, [string]$Hash) {
    $target = Join-Path $Directory $Name
    if (-not (Test-Path -LiteralPath $target)) { Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $target }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $Hash) { throw "Checksum mismatch: $Name" }
    return $target
}
$compiler = Get-Pinned 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' 'innosetup-6.7.3.exe' '9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732'
$signature = Get-AuthenticodeSignature -LiteralPath $compiler
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Pyrsys B.V.') { throw 'Unexpected compiler Authenticode signature.' }
$compilerDirectory = Join-Path $Directory 'inno-6.7.3'
if (-not (Test-Path -LiteralPath (Join-Path $compilerDirectory 'ISCC.exe'))) {
    $process = Start-Process -FilePath $compiler -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/CURRENTUSER','/NOICONS','/TASKS=""',('/DIR="' + $compilerDirectory + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Compiler setup failed: $($process.ExitCode)" }
}
$archive = Get-Pinned 'https://nodejs.org/dist/v22.23.3/node-v22.23.3-win-x64.zip' 'node-v22.23.3-win-x64.zip' '2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71'
if (-not (Test-Path -LiteralPath (Join-Path $Directory 'node-v22.23.3-win-x64/node.exe'))) {
    Expand-Archive -LiteralPath $archive -DestinationPath $Directory
}
Write-Output "Verified installer tools: $Directory"
