"""Render Marea's menu/settings/art on one monitor without desktop input.

Uses an owned SMTC player, isolated settings, mocked startup writes and no
hotkeys/system commands. This is not a Spotify/YouTube application test.
"""
from pathlib import Path
import argparse, ctypes, json, os, subprocess, tempfile, time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--binary', type=Path, required=True)
p.add_argument('--fixture', type=Path, required=True)
p.add_argument('--screen', required=True)
args = p.parse_args()
root = Path(__file__).resolve().parents[1]
binary, fixture = args.binary.resolve(), args.fixture.resolve()
work = Path(tempfile.mkdtemp(prefix='marea personalization ñ '))
scene = work / 'personalization.plm'
source = (root / 'marea-desktop.plm').read_text(encoding='utf-8')
for folder in ['common', 'lang', 'shaders', 'assets', 'wardrobe']:
    source = source.replace('"' + folder + '/', '"' + (root / folder).as_posix() + '/')
source = source.replace('scene Marea {', '''scene Personalization {
    event fixture_menu ->
    event fixture_settings ->
    event fixture_media ->
    event fixture_verify ->
    fact fixture_passed = false
    text fixture_art = ""
''', 1)
# Keep the native non-activating layer; never request physical keyboard focus.
import re
source = re.sub(r'keyboard: on_demand[^\n]*', 'keyboard: none', source)
source = source.replace('reserve: 72 while taking_room', 'reserve: 0')
scene.write_text(source, encoding='utf-8')
env = dict(os.environ, APPDATA=str(work / 'state'), LOCALAPPDATA=str(work / 'cache'),
    PLEAMAR_SOCKET_DIR='personalization-' + str(os.getpid()), PLEAMAR_NO_RELAUNCH='1',
    MAREA_SEARCH_HOTKEY='', LANG='en_US.UTF-8')
settings = work / 'state/pleamar/personalization'
settings.mkdir(parents=True)
(settings / 'settings.json').write_text(json.dumps({'language':'spanish','home':args.screen,'skin':'classic','shelf_folded':True}), encoding='utf-8')
foreground = ctypes.windll.user32.GetForegroundWindow()
with (work / 'player.log').open('w', encoding='utf-8') as player_log, (work / 'native.log').open('w', encoding='utf-8') as render_log:
    player = subprocess.Popen([str(fixture), '--art', '--screen', args.screen], stdout=player_log, stderr=player_log, creationflags=subprocess.CREATE_NO_WINDOW)
    process = None
    try:
        time.sleep(1)
        assert player.poll() is None, 'Media fixture failed to start'
        expected = f'org.pleamar.validation.media.{player.pid}'
        prelude = 'local expected = ' + json.dumps(expected) + '\n' + r'''
local real_sys = sys
local startup = false
local run = function(command, args, callback)
    if command == "powershell.exe" then
        local action = args[#args]
        if action == "enable" then startup = true elseif action == "disable" then startup = false end
        after(20,function() callback(json.encode({available=true,enabled=startup,registered=startup}),0) end)
    elseif callback then after(20,function() callback("",1) end) end
end
local sys = setmetatable({
    watch = function(name, callback)
        if name == "media" then return real_sys.watch(name,function(value)
            callback(value.player == expected and value or {available=false})
        end) end
        return true
    end,
    ask_async = function(name,args,callback)
        if name == "media.state" then return real_sys.ask_async(name,args,callback) end
        after(20,function() callback({},nil) end)
    end,
    call_async = function(name,args,callback)
        if name:sub(1,6) == "media." then
            assert(args[1] == expected); return real_sys.call_async(name,args,callback)
        end
        if callback then after(20,function() callback("",0) end) end
    end,
}, {__index=real_sys})
'''
        post = r'''
on("fixture_menu",function()
    fact.open=false; fact.menu_open=true
end)
on("fixture_settings",function()
    fact.menu_open=false; fact.open=true; fact.page="settings"; fact.section="menu"
end)
on("fixture_media",function()
    fact.menu_open=false; fact.open=true; fact.page="none"
end)
on("fixture_verify",function()
    assert(fact.locale == "es")
    assert(model.entries[1].title == (fact.windows_shelf_folded and "Mostrar aplicaciones" or "Recoger aplicaciones"))
    assert(model.entries[1].group_name == "Escritorio")
    for _, e in ipairs(model.entries) do assert(e.title ~= "Her library" and e.title ~= "History") end
    assert(fact.windows_media_available and fact.windows_media_has_art)
    assert(#model.windows_media_cover == 1)
    text.fixture_art = model.windows_media_cover[1].pic
    fact.fixture_passed = true
end)
after(400,function() fact.hidden=false; fact.needed=true; fact.home=0 end)
'''
        scene.with_suffix('.luau').write_text(prelude + (root / 'marea-desktop.luau').read_text(encoding='utf-8') + post, encoding='utf-8')
        process = subprocess.Popen([str(binary), '--scene', str(scene), '--screen', args.screen, '--no-hud', '--stall','0','--seconds','55'], cwd=root, env=env, stdout=render_log, stderr=render_log, creationflags=subprocess.CREATE_NO_WINDOW)
        def ask(command):
            return subprocess.check_output([str(binary),'--say',scene.stem,command], env=env, text=True, encoding='utf-8', stderr=subprocess.DEVNULL, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW).strip()
        def wait(name, value, timeout=25):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    if ask('get ' + name) == value: return
                except subprocess.SubprocessError: pass
                time.sleep(.15)
            raise AssertionError(f'Timed out waiting for {name}={value}: ' + (work/'native.log').read_text(encoding='utf-8')[-2500:])
        wait('windows_initialized','true')
        wait('windows_media_has_art','true')
        ask('emit fixture_menu'); time.sleep(.5)
        ask('emit fixture_verify'); wait('fixture_passed','true')
        first = Path(ask('get fixture_art'))
        assert first.is_file()
        ask('emit menu_entry 0'); wait('windows_shelf_folded','false')
        ask('fact fixture_passed false'); ask('emit fixture_verify'); wait('fixture_passed','true')
        ask('emit fixture_settings'); time.sleep(.5)
        ask('emit windows_toggle_startup'); wait('windows_startup_enabled','true')
        ask('emit windows_toggle_startup'); wait('windows_startup_enabled','false')
        ask('emit fixture_media'); time.sleep(.5)
        ask('emit next'); time.sleep(2)
        ask('fact fixture_passed false'); ask('emit fixture_verify'); wait('fixture_passed','true')
        second = Path(ask('get fixture_art'))
        assert second.is_file() and second != first and second.read_bytes() != first.read_bytes()
        assert ctypes.windll.user32.GetForegroundWindow() == foreground, 'Test stole physical keyboard focus'
        print('PASS: native DISPLAY menu translation/folding, startup toggle feedback (mock writes), real GSMTC artwork/track change, unchanged foreground')
        print('Evidence:', work)
    finally:
        if process and process.poll() is None:
            try: ask('quit'); process.wait(timeout=12)
            except (subprocess.SubprocessError, OSError): process.terminate(); process.wait(timeout=10)
        player.terminate(); player.wait(timeout=10)
    output = (work/'native.log').read_text(encoding='utf-8')
    assert 'runtime error:' not in output and 'first frame' in output, output[-5000:]
