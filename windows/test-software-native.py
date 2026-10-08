"""Native PowerShell transport/cancellation tests, with optional read-only WinGet checks."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
HOST = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
PREFIX = [str(HOST), '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File']

MOCK = r'''
function Get-WinGetPackage {
    param($Source)
    if ($Source -ne 'winget') { throw 'Wrong source' }
    [pscustomobject]@{Id='Fixture.Update'; Name='Fixture ñ 日本語'; Source='winget'; IsUpdateAvailable=$true; InstalledVersion='1'; AvailableVersions=@('2')}
    [pscustomobject]@{Id='Fixture.Unknown'; Name='Unknown'; Source='winget'; IsUpdateAvailable=$true; InstalledVersion='Unknown'; AvailableVersions=@('9')}
}
function Find-WinGetPackage {
    param($Query,$Source,$Count)
    [pscustomobject]@{Id='Fixture.New'; Name=$Query; Version='3'; Source=$Source}
}
function Install-WinGetPackage {
    [CmdletBinding()] param($Id,$Version,$Source,$MatchOption,$Mode)
    if ($Source -ne 'winget' -or $MatchOption -ne 'Equals' -or $Mode -ne 'Silent' -or $Version -ne '2') { throw 'Unsafe install arguments' }
    if ($Id -eq 'Fixture.Throw') { throw 'Owned fixture exception' }
    Write-Progress -Id 2 -Activity $Id -Status Installing -PercentComplete 25
    if ($Id -eq 'Fixture.Cancel') { Start-Sleep -Seconds 30 } else { Start-Sleep -Milliseconds 250 }
    $value = [pscustomobject]@{Id=$Id; Status=$(if($Id -eq 'Fixture.Fail'){'InstallerError'}else{'Ok'}); RebootRequired=$true}
    $value | Add-Member ScriptMethod Succeeded { $this.Status -eq 'Ok' }
    $value | Add-Member ScriptMethod ErrorMessage { 'Owned fixture failure' }
    return $value
}
function Update-WinGetPackage {
    [CmdletBinding()] param($Id,$Version,$Source,$MatchOption,$Mode)
    Install-WinGetPackage @PSBoundParameters
}
Export-ModuleMember -Function Get-WinGetPackage,Find-WinGetPackage,Install-WinGetPackage,Update-WinGetPackage
'''


def invoke(script, payload):
    result = subprocess.run(PREFIX + [str(script)], input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, encoding='utf-8', timeout=100, creationflags=FLAGS)
    records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert records and records[-1]['type'] == 'result', (result.stdout, result.stderr)
    return result.returncode, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Also read the real catalogue and installed update list; never install or update')
    args = parser.parse_args()
    if os.name != 'nt': parser.error('Run this test on Windows')
    with tempfile.TemporaryDirectory(prefix='marea software ñ ') as temporary:
        folder = Path(temporary)
        (folder / 'mock.psm1').write_text(MOCK, encoding='utf-8-sig')
        script = folder / 'invoke.ps1'
        helper = str(ROOT / 'tools/software.ps1').replace("'", "''")
        script.write_text(". '" + helper + "' -Library\n" + r'''
[Console]::InputEncoding = New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
try { Invoke-MareaSoftware ([Console]::In.ReadToEnd() | ConvertFrom-Json) -ModulePath (Join-Path $PSScriptRoot 'mock.psm1') }
catch { Write-SoftwareRecord @{type='result';ok=$false;error=$_.Exception.Message}; exit 1 }
''', encoding='utf-8-sig')
        _, records = invoke(script, dict(action='scan'))
        assert records[-1]['ok'] and len(records[-1]['items']) == 1 and records[-1]['items'][0]['name'] == 'Fixture ñ 日本語', records
        query = 'ñ 日本語; $(not a command)'
        _, records = invoke(script, dict(action='search', query=query))
        assert records[-1]['ok'] and records[-1]['items'][0]['name'] == query, records
        package = lambda identity: dict(id=identity, name=identity, version='2')
        _, records = invoke(script, dict(action='update', packages=[package('Fixture.Update'), package('Fixture.Fail')]))
        result = records[-1]
        assert not result['ok'] and result['completed'] == ['Fixture.Update'] and result['reboot'], records
        assert any(r['type'] == 'progress' and r['percent'] == 25 for r in records), records
        _, records = invoke(script, dict(action='update', packages=[package('Fixture.Update'), package('Fixture.Throw')]))
        assert not records[-1]['ok'] and records[-1]['completed'] == ['Fixture.Update'] and records[-1]['reboot'], records
        _, records = invoke(script, dict(action='install', packages=[package('Fixture.New')]))
        assert records[-1]['ok'] and records[-1]['completed'] == ['Fixture.New'], records
        code, records = invoke(script, dict(action='install', packages=[package('bad;command')]))
        assert code != 0 and not records[-1]['ok'], records
        process = subprocess.Popen(PREFIX + [str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding='utf-8', creationflags=FLAGS)
        try:
            process.stdin.write(json.dumps(dict(action='install',packages=[package('Fixture.Update'), package('Fixture.Cancel')])))
            process.stdin.close()
            started = json.loads(process.stdout.readline())
            assert started['type'] == 'started'
            # Cancel after the first installer has completed, during the second.
            while True:
                progress = json.loads(process.stdout.readline())
                if progress.get('type') == 'progress' and progress.get('item') == 'Fixture.Cancel': break
            began = time.monotonic()
            code, _ = invoke(ROOT / 'tools/software.ps1', dict(action='cancel', token=started['token']))
            assert code == 0
            process.wait(timeout=8)
            records = [json.loads(line) for line in process.stdout.read().splitlines()]
            assert records[-1]['cancelled'] and not records[-1]['ok'], records
            assert records[-1]['completed'] == ['Fixture.Update'] and records[-1]['reboot'], records
            assert time.monotonic() - began < 8
        finally:
            if process.poll() is None: process.kill(); process.wait(timeout=5)
    print('PASS: native UTF-8/JSON, exact identities, unknown-version exclusion, progress, partial failure, install protocol and named-event cancellation with an owned mock provider')
    if args.live:
        for payload in [dict(action='search',query='Microsoft.PowerShell'), dict(action='scan')]:
            code, records = invoke(ROOT / 'tools/software.ps1', payload)
            assert code == 0 and records[-1]['ok'], records
            assert isinstance(records[-1]['items'], list)
            print(f"PASS: real WinGet {payload['action']}: {len(records[-1]['items'])} structured records; read-only")


if __name__ == '__main__': main()
