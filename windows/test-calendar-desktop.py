"""Validate real Marea calendar delivery with isolated events and an owned toast/shortcut."""
from pathlib import Path
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding='utf-8')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', required=True, type=Path)
parser.add_argument('--hold', type=int, default=0, help='Seconds to leave the test desktop available for inspection')
parser.add_argument('--existing-publisher', action='store_true', help='Use the installed publisher without creating or modifying a shortcut')
args = parser.parse_args()
if sys.platform != 'win32':
    parser.error('This test needs a real Windows desktop')
root = Path(__file__).resolve().parents[1]
binary = args.binary.resolve()
name = f'marea-calendar-validation-{os.getpid()}'
scene, logic = root / f'{name}.plm', root / f'{name}.luau'
title = f'Pleamar calendar validation {os.getpid()} · España & <海>'
shortcut = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs' / f'{name}.lnk'
owned = []
process = None
try:
    with tempfile.TemporaryDirectory(prefix='marea calendar ñ ') as folder:
        state = Path(folder)
        for path in ((scene, logic) if args.existing_publisher else (scene, logic, shortcut)):
            with path.open('x', encoding='utf-8'):
                pass
            owned.append(path)
        env = dict(os.environ, APPDATA=folder, PLEAMAR_SOCKET_DIR=name, PLEAMAR_TEST_WINDOWS='1',
                   PLEAMAR_NO_RELAUNCH='1', MAREA_SEARCH_HOTKEY='', LANG='es_ES.UTF-8', LC_ALL='C.UTF-8',
                   CLAUDE_CONFIG_DIR=str(state / 'claude'), CODEX_HOME=str(state / 'codex'))
        (state / 'claude').mkdir()
        (state / 'claude/.claude.json').write_text('null', encoding='utf-8')
        (state / 'codex/sessions').mkdir(parents=True)
        link_script = state / 'shortcut.ps1'
        link_script.write_text('''$ErrorActionPreference = 'Stop'
$link = (New-Object -ComObject WScript.Shell).CreateShortcut($env:TEST_TOAST_SHORTCUT)
$link.TargetPath = $env:TEST_TOAST_BINARY
$link.Arguments = '--version'
$link.Save()
''', encoding='utf-8')
        if not args.existing_publisher:
            subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-File', str(link_script)], check=True,
                           env=dict(os.environ, TEST_TOAST_SHORTCUT=str(shortcut), TEST_TOAST_BINARY=str(binary)),
                           creationflags=subprocess.CREATE_NO_WINDOW)
            subprocess.run([str(binary), '--register-notification-shortcut', str(shortcut)], check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        scene.write_text((root / 'marea-desktop.plm').read_text(encoding='utf-8').replace('scene Marea {',
            'scene Marea {\n    fact test_notice = false\n    event test_dismiss ->', 1), encoding='utf-8')
        logic.write_text((root / 'marea-desktop.luau').read_text(encoding='utf-8') + '''
local own_notice
native_sys.watch("notifications", function(list)
    own_notice = nil
    for _, n in ipairs(list) do
        if n.title == ''' + json.dumps('Calendario · ' + title, ensure_ascii=False) + ''' then own_notice = n.id end
    end
    fact.test_notice = own_notice ~= nil
end)
on("test_dismiss", function()
    if own_notice then native_sys.call_async("notifications.dismiss", {own_notice}, function(error, code)
        assert(code == 0, error)
    end) end
end)
''', encoding='utf-8')
        calendar = state / 'pleamar' / name / 'calendar.json'
        calendar.parent.mkdir(parents=True)
        now = datetime.datetime.now()
        calendar.write_text(json.dumps({'events': [{'title': title, 'date': now.strftime('%Y-%m-%d'),
                                                   'time': now.strftime('%H:%M')}]}), encoding='utf-8')
        subprocess.run([str(binary), '--check', str(scene)], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        with (state / 'runtime.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([str(binary), '--scene', str(scene), '--no-hud', '--stall', '0'],
                env=env, cwd=state, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            def ask(command):
                return subprocess.check_output([str(binary), '--say', name, command], env=env,
                    text=True, encoding='utf-8', errors='replace', timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW, stderr=subprocess.DEVNULL).strip()

            def expect(field, value, seconds=45):
                deadline = time.monotonic() + seconds
                actual = 'not ready'
                while time.monotonic() < deadline:
                    try:
                        actual = ask(f'get {field}')
                        if actual == value:
                            return
                    except subprocess.SubprocessError:
                        pass
                    if process.poll() is not None:
                        break
                    time.sleep(.15)
                raise AssertionError(f'{field}: expected {value}, got {actual}')

            try:
                expect('windows_initialized', 'true')
                expect('test_notice', 'true')
                saved = json.loads(calendar.read_text(encoding='utf-8'))['events'][0]
                assert saved.get('told') is True and len(saved['notice_tag']) == 16, saved
                print('PASS: actual Marea calendar event reached Windows and was persisted as delivered', flush=True)
                if args.hold:
                    print(f'Inspection process={process.pid}; socket={name}; APPDATA={state}; scene={name}', flush=True)
                    time.sleep(min(args.hold, 600))
                # Reload the real logic and keep the same persistent receipt.
                logic.write_text(logic.read_text(encoding='utf-8') + '\n-- validation reload\n', encoding='utf-8')
                time.sleep(1)
                expect('windows_initialized', 'true')
                expect('test_notice', 'true')
                assert json.loads(calendar.read_text(encoding='utf-8'))['events'][0]['notice_tag'] == saved['notice_tag']
                ask('emit test_dismiss')
                expect('test_notice', 'false', 10)
                time.sleep(21)
                expect('test_notice', 'false', 2)
                assert json.loads(calendar.read_text(encoding='utf-8'))['events'][0]['told'] is True
                output = (state / 'runtime.log').read_text(encoding='utf-8')
                assert 'runtime error:' not in output, output
                print('PASS: logic reload retained the receipt; native dismissal stayed dismissed after the next calendar tick')
            except Exception:
                print((state / 'runtime.log').read_text(encoding='utf-8'))
                raise
            finally:
                if process.poll() is None:
                    try:
                        ask('emit test_dismiss')
                        ask('quit')
                        process.wait(timeout=15)
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=10)
finally:
    for path in reversed(owned):
        path.unlink(missing_ok=True)
