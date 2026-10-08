param(
    [string]$PleamarBinary,
    [string]$DerivaWorkerBinary,
    [string]$AgentHostBinary,
    [string]$WindowManagerBinary,
    [string]$WindowManagerHost,
    [string]$WindowManagerLicense,
    [string]$NodeDirectory,
    [string]$Prefix
)
$ErrorActionPreference = 'Stop'
# Keep one implementation and its defaults for both public entry points.
& (Join-Path $PSScriptRoot 'install-desktop.ps1') @PSBoundParameters
