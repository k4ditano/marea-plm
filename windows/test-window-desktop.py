"""Native shelf rehearsal with eight owned windows and physical Marea actions.

The copied profile filters only the window subscription to the owned fixture's
class. Native enumeration/restoration and the shelf implementation are real;
no user application can be restored by this rehearsal. It does not test HWND
reuse, hung applications, or forced foreground-policy denial.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--fixture', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True, help='New directory for copied sources, logs and results')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
binary, fixture, output = args.binary.resolve(), args.fixture.resolve(), args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
app = output / 'app'
app.mkdir()
for folder in ('common', 'lang', 'wardrobe', 'shaders', 'assets', 'tools'):
    shutil.copytree(root / folder, app / folder)
scene = app / 'marea-desktop.plm'
scene.write_text((root / scene.name).read_text(encoding='utf-8').replace(
    '    fact windows_initialized = false', '    fact windows_initialized = false\n    fact windows_test_minimized = 0'), encoding='utf-8')
logic = (root / 'marea-desktop.luau').read_text(encoding='utf-8')
needle = '    set_stones(v and v.list)'
assert logic.count(needle) == 1
logic = logic.replace(needle, '''    local owned, minimized = {}, 0
    for _, window in ipairs((v and v.list) or {}) do
        if window.class == "PleamarWindowFixture" then
            owned[#owned + 1] = window
            if window.minimized then minimized += 1 end
        end
    end
    fact.windows_test_minimized = minimized
    set_stones(owned)''')
scene.with_suffix('.luau').write_text(logic, encoding='utf-8')
state, command = output / 'fixture-state.json', output / 'fixture-command.txt'
env = dict(os.environ, APPDATA=str(output / 'state'), PLEAMAR_SOCKET_DIR='window-shelf-desktop',
           PLEAMAR_TEST_WINDOWS='1', PLEAMAR_NO_RELAUNCH='1', MAREA_SEARCH_HOTKEY='',
           LANG='es_ES.UTF-8', LC_ALL='C.UTF-8')
native = runtime = None
report = {'complete': False, 'scope': __doc__, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'source_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (root / 'marea-desktop.plm', root / 'marea-desktop.luau', root / 'windows/window-shelf.luau')}}

def snapshot():
    try: return json.loads(state.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError): return None

def send(value):
    pending = command.with_suffix('.pending')
    pending.write_text(value + '\n', encoding='utf-8')
    pending.replace(command)

def ask(value):
    return subprocess.check_output([str(binary), '--say', scene.stem, value], env=env,
        text=True, encoding='utf-8', timeout=10, creationflags=subprocess.CREATE_NO_WINDOW).strip()

def wait(predicate, seconds=45):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if predicate(): return
        for process in (native, runtime):
            if process and process.poll() is not None: raise RuntimeError('Fixture/runtime exited early')
        time.sleep(.15)
    raise TimeoutError('Native shelf condition timed out')

def expect(name, value):
    def ready():
        try: return ask('get ' + name) == value
        except subprocess.CalledProcessError: return False
    wait(ready)

def counts(total, minimized):
    value = snapshot()
    return value and len(value['windows']) == total and sum(w['minimized'] for w in value['windows']) == minimized

try:
    subprocess.run([str(binary), '--check', str(scene)], check=True, stdout=subprocess.DEVNULL)
    with (output / 'fixture.log').open('w', encoding='utf-8') as fixture_log, (output / 'marea.log').open('w', encoding='utf-8') as runtime_log:
        native = subprocess.Popen([str(fixture), '--control', str(command), '--state', str(state)],
            stdout=fixture_log, stderr=fixture_log, creationflags=subprocess.CREATE_NO_WINDOW)
        wait(lambda: counts(8, 8))
        report['initial_fixture'] = snapshot()
        runtime = subprocess.Popen([str(binary), '--scene', str(scene), '--no-hud', '--stall', '0'], env=env,
            cwd=app, stdout=runtime_log, stderr=runtime_log, creationflags=subprocess.CREATE_NO_WINDOW)
        report['pids'] = {'marea': runtime.pid, 'fixture': native.pid}
        expect('windows_initialized', 'true')
        expect('windows_test_minimized', '8')
        wait(lambda: 'first frame' in (output / 'marea.log').read_text(encoding='utf-8'))
        ask('fact skin classic')
        report['initial_stones'] = [{k: ask(f'get stones.{index}.{k}') for k in ('title', 'present', 'seq')} for index in range(6)]
        assert all(row['present'] == 'true' for row in report['initial_stones'])
        first = 0
        target = next(i for i, window in enumerate(snapshot()['windows']) if window['title'] == report['initial_stones'][first]['title'])
        send(f'rename {target}')
        expect(f'stones.{first}.title', 'Pleamar shelf fixture renamed — 世界 🚀')
        assert ask(f'get stones.{first}.seq') == report['initial_stones'][first]['seq']
        report['renamed_slot'] = first
        send(f'close {target}')
        wait(lambda: counts(7, 7))
        expect('windows_test_minimized', '7')
        wait(lambda: all('renamed' not in ask(f'get stones.{i}.title') or ask(f'get stones.{i}.present') == 'false' for i in range(6)))
        (output / 'ready.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('READY: click one of Marea\'s six stones; seven real fixture windows are minimized.', flush=True)
        wait(lambda: counts(7, 6), seconds=480)
        report['after_stone_click'] = snapshot()
        expect('windows_test_minimized', '6')
        send('minimize 1')
        wait(lambda: counts(7, 7))
        expect('windows_test_minimized', '7')
        ask('emit search')
        print('READY: in Marea search, type "restaurar" and choose "Bring back every window" (translated label may vary).', flush=True)
        wait(lambda: counts(7, 0), seconds=480)
        expect('windows_test_minimized', '0')
        report['after_restore_all'] = snapshot()
        report['status'] = ask('get windows_status')
        assert all(ask(f'get stones.{i}.present') == 'false' for i in range(6))
        ask('quit')
        runtime.wait(timeout=15)
        send('quit')
        native.wait(timeout=10)
        report['exit_codes'] = {'marea': runtime.returncode, 'fixture': native.returncode}
        assert runtime.returncode == 0 and native.returncode == 0
        text = (output / 'marea.log').read_text(encoding='utf-8')
        assert 'runtime error:' not in text and 'panicked at' not in text
        report['complete'] = True
finally:
    for process, stop in ((runtime, lambda: ask('quit')), (native, lambda: send('quit'))):
        if process and process.poll() is None:
            try: stop(); process.wait(timeout=15)
            except Exception: process.kill(); process.wait(timeout=10); report['forced_cleanup'] = True
    (output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print('PASS: eight-window catalog, stable Unicode rename, removal, physical stone and restore-all beyond six windows', flush=True)
