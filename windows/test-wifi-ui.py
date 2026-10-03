"""Render Marea with 21 simulated networks; verify actual mouse navigation.

Stop your usual Marea first. In the test panel, open Red, scroll to row 08,
click Siguiente twice, choose row 21, dismiss the diagnostic notice, use
Anterior, then close the panel. No Wi-Fi or Bluetooth command reaches Windows.
Other panel pages still use native services; this test is only for the radio UI.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True, help='New directory for fixture, isolated state and evidence')
args = parser.parse_args()
root, binary, output = Path(__file__).resolve().parents[1], args.binary.resolve(), args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
app, state = output / 'app', output / 'state'
app.mkdir()
(state / 'codex/sessions').mkdir(parents=True)
(state / 'claude').mkdir()
(state / 'claude/.claude.json').write_text('null', encoding='utf-8')
for folder in ['common', 'lang', 'wardrobe', 'shaders', 'assets', 'tools']:
    shutil.copytree(root / folder, app / folder)
scene = app / 'marea-desktop.plm'
plm = (root / scene.name).read_text(encoding='utf-8')
marker = 'scene Marea {'
assert plm.count(marker) == 1
scene.write_text(plm.replace(marker, marker + '''
    text fixture_command = ""
    text fixture_target = ""
    fact fixture_calls = 0
'''), encoding='utf-8')
logic = (root / 'marea-desktop.luau').read_text(encoding='utf-8')
hook = 'install_device_controls(native_sys, notice)'
assert logic.count(hook) == 1
fixture = r'''
local radio_watches = {}
local radio_state = { available = true, present = true, enabled = true, networks = {} }
for index = 1, 21 do
    table.insert(radio_state.networks, { interface = "fixture-adapter", ssid = string.format("%04X", index),
        profile = "fixture-" .. index, name = string.format("Prueba Wi-Fi %02d", index),
        current = false, signal = 1 - index / 100, secure = true, known = true, joinable = true })
end
install_device_controls({
    watch = function(name, callback) radio_watches[name] = callback end,
    ask_async = function(name, _, done)
        if name == "network.wifi" then done(radio_state, nil)
        else done({ available = true, present = false, enabled = false, devices = {} }, nil) end
    end,
    call_async = function(name, args, done)
        if name == "network.scan" then done("", 0); return end
        text.fixture_command = name
        text.fixture_target = table.concat(args, "|")
        fact.fixture_calls += 1
        done("Prueba de interfaz: no se ha enviado ninguna conexion al sistema.", -1)
    end,
}, notice)
after(1000, function()
    radio_watches["network.wifi"](radio_state)
    radio_watches.bluetooth({ available = true, present = false, enabled = false, devices = {} })
end)
'''
scene.with_suffix('.luau').write_text(logic.replace(hook, fixture), encoding='utf-8')
env = dict(os.environ, APPDATA=str(state), PLEAMAR_SOCKET_DIR=f'marea-wifi-ui-{os.getpid()}',
    PLEAMAR_TEST_WINDOWS='1', MAREA_SEARCH_HOTKEY='', PLEAMAR_NO_RELAUNCH='1',
    CODEX_HOME=str(state / 'codex'), CLAUDE_CONFIG_DIR=str(state / 'claude'), LANG='es_ES.UTF-8')
report = {'complete': False, 'simulated_radios': True, 'snapshots': []}
process = None


def ask(command):
    return subprocess.check_output([str(binary), '--say', scene.stem, command], env=env,
        encoding='utf-8', stderr=subprocess.DEVNULL, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW).strip()


def save():
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


try:
    with (output / 'native.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([str(binary), '--scene', str(scene), '--no-hud', '--stall', '0'],
            env=env, cwd=app, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                if ask('get windows_initialized') == 'true' and ask('get windows_wifi_next') == 'true':
                    break
            except subprocess.SubprocessError:
                pass
            if process.poll() is not None:
                raise RuntimeError('Runtime exited before initialization')
            time.sleep(.1)
        else:
            raise RuntimeError('Profile did not initialize')
        ask('fact windows_notice false')
        ask('fact open true')
        print(__doc__, flush=True)
        previous = None
        deadline = time.monotonic() + 360
        while time.monotonic() < deadline:
            current = {name: ask('get ' + name) for name in [
                'windows_wifi_page', 'windows_wifi_previous', 'windows_wifi_next',
                'windows_notice', 'page', 'open', 'fixture_command', 'fixture_target', 'fixture_calls']}
            if current != previous:
                report['snapshots'].append(current)
                save()
                print(json.dumps(current), flush=True)
                previous = current
            if current['open'] == 'false':
                break
            time.sleep(.3)
        else:
            raise RuntimeError('Physical inspection timed out')
        snapshots = report['snapshots']
        assert any(row['windows_wifi_page'] == '9–16 / 21' and row['fixture_calls'] == '0' for row in snapshots)
        assert any(row['windows_wifi_page'] == '17–21 / 21' and row['fixture_calls'] == '0' for row in snapshots), 'Pagination selected a hidden row'
        assert any(row['fixture_command'] == 'network.connect' and row['fixture_target'] == 'fixture-adapter|fixture-21'
            and row['fixture_calls'] == '1' for row in snapshots), 'The selected identity was not network 21'
        assert any(row['windows_wifi_page'] == '9–16 / 21' and row['fixture_calls'] == '1' for row in snapshots), 'Previous page was not reached after selection'
        assert snapshots[-1]['fixture_calls'] == '1' and snapshots[-1]['windows_notice'] == 'false'
        assert 'runtime error:' not in (output / 'native.log').read_text(encoding='utf-8')
        report['complete'] = True
        print('PASS: native rendering and physical Wi-Fi pagination/selection with simulated radios; no hardware connection test')
finally:
    if process is not None and process.poll() is None:
        try:
            ask('quit')
            process.wait(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
                report['forced_cleanup'] = True
    report['exit_code'] = process.returncode if process is not None else None
    save()
