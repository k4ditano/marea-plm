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

def fnv(value):
    result=0xcbf29ce484222325
    for byte in value.encode('utf-8'): result=((result^byte)*0x100000001b3)&0xffffffffffffffff
    return result

def toast_key(engine):
    app=f'org.pleamar.desktop.{fnv(str(engine).replace(chr(47),chr(92)).lower()):016x}'
    clsid=uuid.UUID(int=0x61e6ee1c8b1a41750000000000000000|fnv(app))
    return 'Software\\Classes\\CLSID\\{'+str(clsid)+'}\\LocalServer32'

def toast_server(engine):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,toast_key(engine),0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as k:
            return winreg.QueryValueEx(k,None)[0]
    except FileNotFoundError: return None

def toast_protocol(engine):
    app=f'org.pleamar.desktop.{fnv(str(engine).replace(chr(47),chr(92)).lower()):016x}'
    key='Software\\Classes\\pleamar-notify-'+f'{fnv(app):016x}'
    values=[]
    for path,name in [(key+'\\shell\\open\\command',None),(key,'URL Protocol')]:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path) as entry:values.append(winreg.QueryValueEx(entry,name)[0])
        except FileNotFoundError:values.append(None)
    return tuple(values)

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
test_environment = dict(os.environ, LOCALAPPDATA=str(output / 'Local data ñ'))
inherited_rules = output / 'personal session ñ.conf'
inherited_rules.write_text('window app=* private\n', encoding='utf-8')
test_environment['PLEAMAR_WM_CONFIG'] = str(inherited_rules)
agent_state = output / 'Local data ñ/Marea/Agent'
agent_state.mkdir(parents=True)
agent_marker = agent_state / 'installer-preserve.txt'
agent_marker.write_text('preserve existing agent state', encoding='utf-8')

def run(command, expect=0, log=None, environment=None):
    result = subprocess.run([str(c) for c in command], capture_output=True, encoding='utf-8', errors='replace',
        timeout=600, creationflags=subprocess.CREATE_NO_WINDOW, env=environment or test_environment)
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

def startup(action='state'):
    return json.loads(run([host,'-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
        target / 'app/tools/startup.ps1','-Action',action]).stdout)

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
    assert inherited_rules.read_text(encoding='utf-8') == 'window app=* private\n'
    report['stages'].append('preflight ignores and preserves inherited personal window rules')
    assert Path(registration()).resolve() == target
    manifest = json.loads((target / 'package.json').read_text(encoding='utf-8'))
    for relative, digest in manifest['files'].items():
        assert hashlib.sha256((target / relative).read_bytes()).hexdigest() == digest, relative
    assert (target / 'logs/setup-registration.txt').read_text(encoding='utf-8-sig') == 'OK'
    agent_cache = target / 'bin/marea-agent-access.txt'
    prepared_cache = agent_cache.read_bytes()
    assert prepared_cache and (target / 'bin/marea-agent.exe').is_file()
    assert manifest['agent_sdk_version']
    assert len(manifest['wm_source']) == 40
    assert (target / 'bin/pleamar-wm.exe').is_file() and (target / 'bin/pleamar-wm-host.exe').is_file()
    for extension in ['plm', 'luau']:
        assert (target / f'app/tools/windows-overview.{extension}').is_file()
    run([target / 'bin/pleamar-wm.exe', '--check', target / 'app/tools/windows-overview.plm'])
    capabilities = json.loads(run([target / 'bin/pleamar-wm.exe', 'capabilities']).stdout)
    assert capabilities['visible_window_capture'] and capabilities['application_dock']
    for extension in ['plm', 'luau']:
        assert (target / f'app/tools/windows-dock.{extension}').is_file()
    run([target / 'bin/pleamar-wm.exe', '--check', target / 'app/tools/windows-dock.plm'])
    report['stages'].append('packaged overview source compiles with matching native capture capability; no GUI test')
    programs = ctypes.create_unicode_buffer(32768)
    assert ctypes.windll.shell32.SHGetFolderPathW(None, 2, None, 0, programs) == 0
    menu = Path(programs.value) / group
    assert (menu / 'Marea.lnk').is_file()
    assert (target / 'bin/pleamar-notifications.exe').is_file()
    assert toast_server(target / 'bin/pleamar.exe')==f'"{target / "bin/pleamar-notifications.exe"}"'
    assert toast_protocol(target / 'bin/pleamar.exe')==(f'"{target / "bin/pleamar-notifications.exe"}" --activate-notification "%1"','')
    run([target / 'bin/pleamar.exe','--check-notification-shortcut',menu / 'Marea.lnk'])
    report['stages'].append('native notification COM/protocol broker and shortcut identity verified; no toast clicked')
    icon = target / 'app/assets/marea.ico'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, flags) as k:
        display_icon = winreg.QueryValueEx(k, 'DisplayIcon')[0]
    assert display_icon in [str(icon), str(icon) + ',0', f'"{icon}"', f'"{icon}",0'], display_icon
    run([host, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', Path(__file__).with_name('test-icons.ps1'), '-Icon', icon,
        '-Setup', setup, '-Uninstaller', target / 'unins000.exe', '-Shortcut', menu / 'Marea.lnk'])
    report['stages'].append('native icon sizes, setup/uninstaller pixels, Start-menu icon and Installed apps registration')
    hook()
    assert agent_cache.read_bytes() == prepared_cache, 'Validation disturbed the installed agent profile cache'
    assert not (target / 'bin/marea-agent-validation-access.txt').exists()
    assert agent_marker.read_text(encoding='utf-8') == 'preserve existing agent state'
    report['stages'].append('native AI SDK starts signed out in a separate profile; installed permissions and state preserved')
    report['stages'].append('silent Unicode install, native Luau/worker/Node and shortcut registration')
    assert startup()['available'] and not startup()['registered']
    assert startup('enable')['enabled']
    # Check that a bad payload cannot pass preflight, independently of compiler CRCs.
    readme = target / 'README.md'
    original = readme.read_bytes()
    readme.write_bytes(b'changed payload')
    hook(expect='failure')
    install('repair-update')
    assert readme.read_bytes() == original
    assert startup()['enabled'], 'Upgrade lost the opt-in startup entry'
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
    assert toast_server(target / 'bin/pleamar.exe') is None
    assert toast_protocol(target / 'bin/pleamar.exe')==(None,None)
    assert not (target / 'bin/pleamar-notifications.exe').exists()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as k:
        try: winreg.QueryValueEx(k, 'Marea')
        except FileNotFoundError: pass
        else: raise AssertionError('Uninstall left Marea startup registered')
    assert not (target / 'bin/pleamar.exe').exists() and not (target / 'bin/deriva-worker.exe').exists()
    assert not (target / 'bin/marea-agent.exe').exists() and not agent_cache.exists()
    assert not (target / 'bin/pleamar-wm.exe').exists() and not (target / 'bin/pleamar-wm-host.exe').exists()
    assert agent_marker.read_text(encoding='utf-8') == 'preserve existing agent state'
    assert (target / 'logs/keep.txt').read_text(encoding='utf-8') == 'user log'
    assert (target / 'keep-user-file.txt').read_text(encoding='utf-8') == 'user file'
    assert not menu.exists()
    assert library_bytes == {f.relative_to(library): f.read_bytes() for f in library.rglob('*') if f.is_file()}
    report['stages'].append('uninstall removes registered package and shortcuts, retains actual Deriva library and user files/logs')
    report['stages'].append('startup off by default, explicit opt-in survives upgrade, own entry removed on uninstall')
    report['passed'] = True
finally:
    # Only uninstall the owned smoke installation; never another registered path.
    location = registration()
    if location and Path(location).resolve() == target and (target / 'unins000.exe').exists():
        run([target / 'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'])
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('PASS: real silent install, update, corruption/lock rejection and uninstall; no desktop or wizard validation')
