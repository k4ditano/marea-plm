"""Native Marea auto-hide, named settings toggle and actual isolated storage.

Only the explicit secondary monitor (or disposable CI desktop) is used.
Local checks use named scene actions without system input. Only disposable CI
moves its pointer over the owned fixture to exercise physical hover/leave routing.
"""
from pathlib import Path
import argparse, ctypes as C, importlib.util, json, os, subprocess, time
from ctypes import wintypes as W

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--monitor')
parser.add_argument('--ci-owned-desktop', action='store_true')
args = parser.parse_args()
assert os.name == 'nt'
ci = args.ci_owned_desktop
if ci:
    assert all(os.environ.get(k) == v for k,v in [('GITHUB_ACTIONS','true'),('RUNNER_ENVIRONMENT','github-hosted'),('MAREA_CI_PROFILE_UI','1')])
else:
    assert args.monitor, 'Choose an explicit secondary display'
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('profile_ui', root / 'windows/test-profile-ui-ci.py')
ui = importlib.util.module_from_spec(spec); spec.loader.exec_module(ui)
desktop = ui.Desktop()
user = desktop.user
class MonitorInfo(C.Structure):
    _fields_ = [('size', W.DWORD), ('bounds', W.RECT), ('work', W.RECT), ('flags', W.DWORD), ('name', W.WCHAR*32)]
monitors = []
callback = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)
user.GetMonitorInfoW.argtypes = [W.HANDLE, C.POINTER(MonitorInfo)]
@callback
def monitor(handle, dc, rect, data):
    info = MonitorInfo(); info.size = C.sizeof(info)
    assert user.GetMonitorInfoW(handle, C.byref(info))
    monitors.append((info.name, bool(info.flags & 1)))
    return True
assert user.EnumDisplayMonitors(None, None, monitor, 0)
selected = monitors[0][0] if ci else args.monitor
assert any(name == selected and (ci or not primary) for name, primary in monitors), (selected, monitors)
user.GetForegroundWindow.restype = W.HWND
binary = args.binary.resolve(strict=True)
output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
scene = output / 'marea-autohide.plm'
source = ui.fixture_source(root).replace('permissions { }', 'permissions { services: "files", "files.*" }')
source = source.replace(' fact fixture_ready = false', ' text fixture_error = ""\n fact fixture_startup_calls = 0\n fact fixture_ready = false')
source = source.replace('    let cy_actual = cy + body.y - rise - away * 84 - 5 * tray - 96 * drop_in',
    '    let cy_actual = cy + body.y - rise - away * 84 - 5 * tray - 96 * drop_in\n'
    '    prop fixture_x = 0 ~16ms\n    prop fixture_y = 0 ~16ms\n    follow fixture_x = cx\n    follow fixture_y = cy_actual')
scene.write_text(source, encoding='utf-8')
module = (root/'windows/auto-hide.luau').read_text(encoding='utf-8')
logic = '''
fact.locale="es"
fact["hosts.0"]=true;fact["hosts.1"]=false;fact["hosts.2"]=false
local ok, settings = pcall(sys.ask, "files.read", "settings.json", "json")
if not ok or type(settings) ~= "table" then settings = {language="spanish", sentinel="Café 日本語"} end
(function() __MODULE__ end)()(settings, sys, function(message) text.fixture_error=message end)
on("fixture_stage", function(stage)
    fact.open=stage==1;fact.page="settings";fact.section="menu"
    if stage==0 then fact.note=false;fact.menu_open=false end
end)
fact.windows_startup_available=true
on("windows_toggle_startup", function() fact.fixture_startup_calls+=1 end)
fact.fixture_ready=true
'''.replace('__MODULE__', module)
scene.with_suffix('.luau').write_text(logic, encoding='utf-8')
env = dict(os.environ, APPDATA=str(output/'state'), LOCALAPPDATA=str(output/'local'),
    PLEAMAR_SOCKET_DIR='autohide-'+str(os.getpid()), PLEAMAR_NO_RELAUNCH='1', MAREA_SEARCH_HOTKEY='', PLEAMAR_TEST_WINDOWS='1')
flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
report = dict(passed=False, monitor=selected, os_input=ci, native_hover=ci,
    real_files_service=True, full_product_acceptance=False, checks=[], images=[])
process = None
def guard():
    assert process.poll() is None, 'Native scene exited'
    assert desktop.pid(user.GetForegroundWindow()) != process.pid, 'Fixture took foreground'
def ask(command):
    response = subprocess.check_output([str(binary),'--say',scene.stem,command], env=env,
        encoding='utf-8',stderr=subprocess.DEVNULL,timeout=5,creationflags=flags).strip()
    # Luau can be ready before the first GPU frame finishes initializing.
    # Retry this transient query timeout only within until's existing deadline;
    # an unknown command or a persistently stalled renderer must still fail.
    if response == '? the render does not answer':
        raise subprocess.TimeoutExpired(command, 5)
    assert not response.startswith('?'), response
    return response
def until(check, label):
    end=time.monotonic()+20
    while time.monotonic()<end:
        guard()
        try:
            if check():return
        except subprocess.SubprocessError:pass
        time.sleep(.08)
    raise AssertionError(label)
def capture(label):
    path=output/(label+'.png');ui.png(path,desktop.pixels(hwnd));report['images'].append(path.name)
def settings():
    files=list((output/'state').rglob('settings.json'));assert len(files)==1
    return json.loads(files[0].read_text(encoding='utf-8'))
def move_pointer(x,y):
    assert ci, 'Never move the pointer on a user desktop'
    guard()
    rect=W.RECT();assert user.GetClientRect(hwnd,C.byref(rect))
    scale=rect.right/820
    point=W.POINT(round(x*scale),round(y*scale))
    assert user.ClientToScreen(hwnd,C.byref(point))
    assert user.SetCursorPos(point.x,point.y)
def start(label):
    global process, hwnd
    log=(output/(label+'.log')).open('w',encoding='utf-8')
    try:
        process=subprocess.Popen([str(binary),'--scene',str(scene),'--screen',selected,'--no-hud','--stall','0'],env=env,stdout=log,stderr=log,creationflags=flags)
    finally:log.close()
    until(lambda: ask('get fixture_ready')=='true','logic initialization')
    until(lambda: desktop.window(process.pid,'pleamar surface 0 · ') is not None,'native main panel')
    hwnd=desktop.window(process.pid,'pleamar surface 0 · ')
def stop():
    ask('quit');assert process.wait(timeout=20)==0
try:
    start('default')
    until(lambda: ask('get hidden')=='true' and float(ask('get out'))<.01,'default auto-hide')
    assert ask('get hosts.0')=='true' and float(ask('get swim.0'))==1
    assert float(ask('get fixture_y'))+23>0, 'Face is entirely above the screen'
    capture('01-tucked')
    initial_tree=json.loads(ask('describe json'))
    (output/'tucked-tree.json').write_text(json.dumps(initial_tree,indent=2,ensure_ascii=False),encoding='utf-8')
    if ci:
        def hover():
            move_pointer(float(ask('get fixture_x')),max(3,float(ask('get fixture_y'))))
            return float(ask('get out'))>.99
        until(hover,'native hover did not reveal Marea')
    else:
        ask('press body_zone')
        until(lambda: float(ask('get out'))>.99 and ask('get open')=='true','named press did not reveal Marea')
    capture('02-revealed')
    if ci:move_pointer(750,600)
    else:
        ask('emit fixture_stage 0')
        assert user.PostMessageW(hwnd,0x2A3,0,0)
    until(lambda: float(ask('get out'))<.01,'leaving did not tuck after the grace period')
    report['checks'].append('Visible face; '+('native pointer hover/leave' if ci else 'named press/closure')+' reveals and tucks after grace')
    ask('emit fixture_stage 1')
    until(lambda: float(ask('get paging'))>.99 and float(ask('get out'))>.99,'open settings were hidden')
    time.sleep(1)
    tree=json.loads(ask('describe json'))
    (output/'settings-tree.json').write_text(json.dumps(tree,indent=2,ensure_ascii=False),encoding='utf-8')
    toggle=next(n for n in ui.nodes(tree) if n.get('label')=='Ocultarse automáticamente')
    assert toggle['role']=='toggle' and toggle['checked'] is True
    capture('03-settings-enabled')
    ask('press '+toggle['name'])
    until(lambda: ask('get hidden')=='false','toggle did not disable auto-hide')
    assert settings()['auto_hide'] is False and settings()['sentinel']=='Café 日本語'
    capture('04-settings-disabled')
    # This second raw grid control had the same cross-monitor zone collision.
    # Only its event is observed: the fixture never changes actual Windows startup.
    ask('wheel windows_settings_list -5')
    until(lambda: any(n.get('label')=='Iniciar con Windows' for n in ui.nodes(json.loads(ask('describe json')))), 'startup tile after scrolling')
    startup=next(n for n in ui.nodes(json.loads(ask('describe json'))) if n.get('label')=='Iniciar con Windows')
    ask('press '+startup['name'])
    until(lambda: ask('get fixture_startup_calls')=='1','other grid toggle lost its press rule')
    stop();start('disabled-restart')
    until(lambda: ask('get hidden')=='false' and float(ask('get out'))>.99,'saved opt-out did not survive restart')
    time.sleep(3.5);assert float(ask('get out'))>.99
    ask('emit fixture_stage 1')
    until(lambda: float(ask('get paging'))>.99,'reopened settings')
    ask('press '+toggle['name'])
    until(lambda: ask('get hidden')=='true','toggle did not enable auto-hide')
    assert settings()['auto_hide'] is True and settings()['sentinel']=='Café 日本語'
    assert float(ask('get out'))>.99,'auto-hide hid an open card'
    stop();start('enabled-restart')
    until(lambda: ask('get hidden')=='true' and float(ask('get out'))<.01,'saved opt-in did not survive restart')
    stop()
    report['checks'].append('Translated named toggle, real settings writes, both choices survive cold restart; open card stays visible')
    report['passed']=True
finally:
    if process and process.poll() is None:
        try:stop()
        except subprocess.SubprocessError:process.kill();process.wait()
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
