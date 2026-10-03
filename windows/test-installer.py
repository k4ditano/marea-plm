"""Real silent install/update/uninstall in an owned Unicode directory; never launch Marea."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
import winreg

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--setup', type=Path, required=True)
parser.add_argument('--payload', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True, help='New directory retained for logs and test data')
args = parser.parse_args()
setup, payload, output = args.setup.resolve(strict=True), args.payload.resolve(strict=True), args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
target = output / 'Installed Marea ñ 海'
group = 'Marea installer test ' + uuid.uuid4().hex
key = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A8D741A8-45D5-4DE8-A38E-27DA65D253F8}_is1'
flags = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
def registration():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, flags) as k:
            return winreg.QueryValueEx(k, 'InstallLocation')[0]
    except FileNotFoundError: return None
assert registration() is None, 'An actual Setup installation exists. Run this smoke test on a clean account/runner.'

def run(command, expect=0, log=None, environment=None):
    result = subprocess.run([str(c) for c in command], capture_output=True, encoding='utf-8', errors='replace',
        timeout=180, creationflags=subprocess.CREATE_NO_WINDOW, env=environment)
    if expect == 'failure': assert result.returncode != 0, 'A rejected installation returned success.'
    else: assert result.returncode == expect, (result.returncode, result.stdout, result.stderr, log)
    return result

def install(label, expect=0):
    log = output / (label + '.log')
    return run([setup, '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-', '/TASKS=',
        '/DIR=' + str(target), '/GROUP=' + group, '/LOG=' + str(log)], expect, log)

host = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
def hook(action='validate', package=target, expect=0):
    return run([host,'-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
        package / 'windows/installer-hooks.ps1','-Package',package,'-Action',action], expect)

report = {'passed': False, 'graphical_validation': False, 'setup_sha256': hashlib.sha256(setup.read_bytes()).hexdigest(), 'stages': []}
try:
    # An arbitrary existing directory must not be adopted or overwritten.
    target.mkdir()
    sentinel = target / 'unrelated.txt'
    sentinel.write_text('preserve unrelated content', encoding='utf-8')
    install('reject-unrelated', 'failure')
    assert sentinel.read_text(encoding='utf-8') == 'preserve unrelated content' and registration() is None
    sentinel.unlink()
    report['stages'].append('unrelated directory rejected without changes')
    install('install')
    assert Path(registration()).resolve() == target
    manifest = json.loads((target / 'package.json').read_text(encoding='utf-8'))
    for relative, digest in manifest['files'].items():
        assert hashlib.sha256((target / relative).read_bytes()).hexdigest() == digest, relative
    assert (target / 'logs/setup-registration.txt').read_text(encoding='utf-8-sig') == 'OK'
    programs = ctypes.create_unicode_buffer(32768)
    assert ctypes.windll.shell32.SHGetFolderPathW(None, 2, None, 0, programs) == 0
    menu = Path(programs.value) / group
    assert (menu / 'Marea.lnk').is_file()
    icon = target / 'app/assets/marea.ico'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, flags) as k:
        display_icon = winreg.QueryValueEx(k, 'DisplayIcon')[0]
    assert display_icon in [str(icon), str(icon) + ',0', f'"{icon}"', f'"{icon}",0'], display_icon
    run([host, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', Path(__file__).with_name('test-icons.ps1'), '-Icon', icon,
        '-Setup', setup, '-Uninstaller', target / 'unins000.exe', '-Shortcut', menu / 'Marea.lnk'])
    report['stages'].append('native icon sizes, setup/uninstaller pixels, Start-menu icon and Installed apps registration')
    hook()
    report['stages'].append('silent Unicode install, native Luau/worker/Node and shortcut registration')
    # Check that a bad payload cannot pass preflight, independently of compiler CRCs.
    readme = target / 'README.md'
    original = readme.read_bytes()
    readme.write_bytes(b'changed payload')
    hook(expect='failure')
    install('repair-update')
    assert readme.read_bytes() == original
    report['stages'].append('changed payload rejected and reinstall restores packaged bytes')
    # Hold a real DLL with no sharing; the update must stop before replacement.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    before = (target / 'package.json').read_bytes()
    lock = kernel.CreateFileW(str(target / 'bin/dxil.dll'), 0x80000000, 0, None, 3, 0, None)
    assert lock not in [None, ctypes.c_void_p(-1).value]
    try: install('locked-update', 'failure')
    finally: kernel.CloseHandle(lock)
    assert (target / 'package.json').read_bytes() == before
    hook()
    report['stages'].append('locked update fails before replacement; prior package still passes')
    (target / 'logs/keep.txt').write_text('user log', encoding='utf-8')
    (target / 'keep-user-file.txt').write_text('user file', encoding='utf-8')
    library = output / 'Deriva library ñ 海'
    run([target / 'bin/deriva-worker.exe', 'ingest', '--request', json.dumps({'type':'text','text':'Keep my library','title':'Installer preservation'})],
        environment=dict(os.environ, MAREA_DERIVA_DIR=str(library)))
    library_bytes = {f.relative_to(library): f.read_bytes() for f in library.rglob('*') if f.is_file()}
    assert library_bytes
    run([target / 'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/LOG=' + str(output / 'uninstall.log')])
    assert registration() is None
    assert not (target / 'bin/pleamar.exe').exists() and not (target / 'bin/deriva-worker.exe').exists()
    assert (target / 'logs/keep.txt').read_text(encoding='utf-8') == 'user log'
    assert (target / 'keep-user-file.txt').read_text(encoding='utf-8') == 'user file'
    assert not menu.exists()
    assert library_bytes == {f.relative_to(library): f.read_bytes() for f in library.rglob('*') if f.is_file()}
    report['stages'].append('uninstall removes registered package and shortcuts, retains actual Deriva library and user files/logs')
    report['passed'] = True
finally:
    # Only uninstall the owned smoke installation; never another registered path.
    location = registration()
    if location and Path(location).resolve() == target and (target / 'unins000.exe').exists():
        run([target / 'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'])
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('PASS: real silent install, update, corruption/lock rejection and uninstall; no desktop or wizard validation')
