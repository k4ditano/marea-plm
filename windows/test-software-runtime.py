"""Render the real software page on one monitor, with read-only WinGet access."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--screen', required=True)
parser.add_argument('--hold', type=int, default=0, help='Keep the checked catalogue visible for screenshot inspection')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='marea software render ñ '))
scene = folder / 'software-profile.plm'
source = (ROOT / 'marea-desktop.plm').read_text(encoding='utf-8')
for name in ['common', 'lang', 'shaders', 'assets', 'wardrobe']:
    source = source.replace('"' + name + '/', '"' + (ROOT / name).as_posix() + '/')
source = re.sub(r'permissions \{.*?\}', 'permissions { run: "powershell.exe"; services: "env" }', source, count=1, flags=re.S)
source = re.sub(r'keyboard: on_demand[^\n]*', 'keyboard: none', source)
source = source.replace('reserve: 72 while taking_room', 'reserve: 0')
scene.write_text(source, encoding='utf-8')
module = (ROOT / 'windows/software.luau').read_text(encoding='utf-8')
helper = json.dumps(str(ROOT / 'tools/software.ps1'))
scene.with_suffix('.luau').write_text('''
fact.demo=false; fact.hidden=false; fact.needed=true; fact.skin="classic"; fact.locale="es"
local hooks = {}
local native_spawn, native_run = spawn, run
local function readonly(start)
    return function(name, args, ...)
        -- This fixture never reaches an installer, even if Confirm is clicked.
        local arguments = {...}
        local options = arguments[#arguments]
        local request = json.decode(options.input)
        assert(request.action == "scan" or request.action == "search", "read-only software fixture")
        local fixed = table.clone(args); fixed[7] = ''' + helper + '''
        return start(name, fixed, table.unpack(arguments))
    end
end
local install = (function()
''' + module + '''
end)()
install(readonly(native_run), readonly(native_spawn), hooks, log)
after(1500, function() hooks.software("updates") end)
''', encoding='utf-8')
env = dict(os.environ, APPDATA=str(folder / 'state'), LOCALAPPDATA=os.environ['LOCALAPPDATA'],
    PLEAMAR_TEST_WINDOWS='1', PLEAMAR_SOCKET_DIR='software-render-' + str(os.getpid()), PLEAMAR_NO_RELAUNCH='1')
user32 = ctypes.WinDLL('user32'); user32.GetForegroundWindow.restype = ctypes.c_void_p
foreground = user32.GetForegroundWindow()
with (folder / 'native.log').open('w', encoding='utf-8') as log:
    process = subprocess.Popen([str(args.binary.resolve()), '--scene', str(scene), '--screen', args.screen + ',' + args.screen,
        '--no-hud', '--stall', '0', '--seconds', str(180 + args.hold)], env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    def ask(command):
        return subprocess.check_output([str(args.binary.resolve()), '--say', scene.stem, command], env=env,
            encoding='utf-8', stderr=subprocess.DEVNULL, timeout=4, creationflags=subprocess.CREATE_NO_WINDOW).strip()
    def wait(name, predicate):
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            if process.poll() is not None: raise RuntimeError((folder / 'native.log').read_text(encoding='utf-8'))
            try:
                value = ask('get ' + name)
                if predicate(value): return value
            except subprocess.SubprocessError: pass
            time.sleep(.15)
        raise AssertionError((name, ask('get ' + name), folder))
    try:
        wait('sw.state', lambda v: v in ('ready','broken'))
        assert ask('get sw.state') == 'ready', ask('get sw.error')
        wait('open', lambda v: v == 'true')
        wait('page', lambda v: v == 'software')
        print('PASS: real software scan rendered; updates=' + ask('get sw.count'), flush=True)
        ask('fact sw.tab catalogue'); ask('text sw.query Microsoft.PowerShell')
        wait('sw.found.count', lambda v: v.isdigit() and int(v) > 0)
        assert ask('get windows_sw_search_error') in ('', '""'), ask('get windows_sw_search_error')
        assert 'first frame' in (folder / 'native.log').read_text(encoding='utf-8')
        print('PASS: real catalogue rendered with native Luau stdin/streamed replies', flush=True)
        print(json.dumps(dict(pid=process.pid, directory=str(folder), socket=env['PLEAMAR_SOCKET_DIR'], scene=scene.stem)), flush=True)
        time.sleep(args.hold)
        assert user32.GetForegroundWindow() == foreground, 'foreground changed during the fixture'
        print('PASS: native software page; foreground unchanged; no application installed or updated', flush=True)
    finally:
        if process.poll() is None:
            try: ask('quit'); process.wait(timeout=10)
            except (OSError, subprocess.SubprocessError): process.terminate(); process.wait(timeout=10)
