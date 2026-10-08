"""Actual generated Marea UI with isolated logic on a disposable CI desktop.

No system input, device services, account, network or model call is exercised.
The screenshots and scene commands cover rendering/layout and named interaction,
not hardware or installed-product acceptance. Never run this on a user's desktop.
"""
from pathlib import Path
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time
import zlib


def require_ci():
    if (sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or os.environ.get('MAREA_CI_PROFILE_UI') != '1'):
        raise RuntimeError('Visible fixture requires the explicit step on a disposable GitHub-hosted Windows runner')


def fixture_source(root, idle_tide_baseline=False):
    source = (root / 'marea-desktop.plm').read_text(encoding='utf-8')
    if idle_tide_baseline:
        guard = 'shader chat_tide { show: chat.stir > 0.001; at:'
        assert source.count(guard) == 1, 'The idle tide optimization changed'
        source = source.replace(guard, 'shader chat_tide { at:', 1)
    for folder in ('common', 'lang', 'shaders', 'assets', 'wardrobe'):
        source = source.replace('"' + folder + '/', '"' + (root / folder).as_posix() + '/')
    source = re.sub(r'keyboard: on_demand[^\n]*', 'keyboard: none', source)
    source = source.replace('reserve: 72 while taking_room', 'reserve: 0')
    # Keep the runner's console out of the evidence without changing the UI.
    assert source.count('\n    // ── where she lives') == 1
    source = source.replace('\n    // ── where she lives',
        '\n    box { from: 0, 0; size: 820, 680; color: #d8e0e5 }\n    // ── where she lives', 1)
    source, count = re.subn(r'permissions\s*\{[^{}]*\}', 'permissions { }', source)
    assert count == 1, 'The fixture must deny every external service'
    assert source.count('scene Marea {') == 1
    source = source.replace('scene Marea {', 'scene MareaProfileCI {\n'
        ' event fixture_stage ->\n fact fixture_ready = false\n fact fixture_volume_calls = 0\n fact fixture_login_calls = 0\n fact fixture_login_opens = 0\n fact fixture_allowed = -1\n fact fixture_denied = -1\n', 1)
    return source


class Desktop:
    def __init__(self):
        self.user = C.WinDLL('user32', use_last_error=True)
        self.gdi = C.WinDLL('gdi32', use_last_error=True)
        self.callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        for lib, name, result, args in [
            (self.user, 'EnumWindows', W.BOOL, [self.callback, W.LPARAM]),
            (self.user, 'GetWindowThreadProcessId', W.DWORD, [W.HWND, C.POINTER(W.DWORD)]),
            (self.user, 'GetWindowTextW', C.c_int, [W.HWND, W.LPWSTR, C.c_int]),
            (self.user, 'IsWindowVisible', W.BOOL, [W.HWND]),
            (self.user, 'SetProcessDpiAwarenessContext', W.BOOL, [W.HANDLE]),
            (self.user, 'GetClientRect', W.BOOL, [W.HWND, C.POINTER(W.RECT)]),
            (self.user, 'ClientToScreen', W.BOOL, [W.HWND, C.POINTER(W.POINT)]),
            (self.user, 'GetDC', W.HDC, [W.HWND]),
            (self.user, 'ReleaseDC', C.c_int, [W.HWND, W.HDC]),
            (self.user, 'PostMessageW', W.BOOL, [W.HWND, W.UINT, W.WPARAM, W.LPARAM]),
            (self.gdi, 'CreateCompatibleDC', W.HDC, [W.HDC]),
            (self.gdi, 'CreateCompatibleBitmap', W.HBITMAP, [W.HDC, C.c_int, C.c_int]),
            (self.gdi, 'SelectObject', W.HANDLE, [W.HDC, W.HANDLE]),
            (self.gdi, 'BitBlt', W.BOOL, [W.HDC, C.c_int, C.c_int, C.c_int, C.c_int, W.HDC, C.c_int, C.c_int, W.DWORD]),
            (self.gdi, 'GetDIBits', C.c_int, [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.c_void_p, W.UINT]),
            (self.gdi, 'DeleteObject', W.BOOL, [W.HANDLE]),
            (self.gdi, 'DeleteDC', W.BOOL, [W.HDC]),
        ]:
            function = getattr(lib, name)
            function.restype, function.argtypes = result, args
        if not self.user.SetProcessDpiAwarenessContext(W.HANDLE(-4)):
            raise C.WinError(C.get_last_error())

    def pid(self, hwnd):
        pid = W.DWORD()
        assert self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        return pid.value

    def window(self, pid, title):
        found = []

        @self.callback
        def visit(hwnd, _):
            text = C.create_unicode_buffer(256)
            self.user.GetWindowTextW(hwnd, text, len(text))
            if text.value.startswith(title) and self.pid(hwnd) == pid and self.user.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True

        assert self.user.EnumWindows(visit, 0)
        assert len(found) <= 1
        return found[0] if found else None

    def pixels(self, hwnd):
        rect, point = W.RECT(), W.POINT()
        assert self.user.GetClientRect(hwnd, C.byref(rect))
        assert self.user.ClientToScreen(hwnd, C.byref(point))
        width, height = rect.right, rect.bottom
        assert 100 <= width <= 4096 and 100 <= height <= 2160
        source = self.user.GetDC(None)
        target = self.gdi.CreateCompatibleDC(source)
        bitmap = self.gdi.CreateCompatibleBitmap(source, width, height)
        assert source and target and bitmap
        old = self.gdi.SelectObject(target, bitmap)
        try:
            # Include the native transparent panel in the runner's composed image.
            assert self.gdi.BitBlt(target, 0, 0, width, height, source, point.x, point.y, 0x40CC0020)
            self.gdi.SelectObject(target, old)
            old = None
            header = C.create_string_buffer(struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0))
            pixels = C.create_string_buffer(width * height * 4)
            assert self.gdi.GetDIBits(target, bitmap, 0, height, pixels, header, 0) == height
            return width, height, pixels.raw
        finally:
            if old:
                self.gdi.SelectObject(target, old)
            self.gdi.DeleteObject(bitmap)
            self.gdi.DeleteDC(target)
            self.user.ReleaseDC(None, source)


def png(path, picture):
    width, height, bgra = picture
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        row = bgra[y * width * 4:(y + 1) * width * 4]
        for i in range(0, len(row), 4):
            rows.extend((row[i + 2], row[i + 1], row[i]))

    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))

    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


FIXTURE_LOGIC = r'''
fact.locale="es"
fact.hidden=false;fact.needed=true;fact.home=0
fact["hosts.0"]=true;fact["hosts.1"]=false;fact["hosts.2"]=false
fact["sound.volume"]=0.42;fact["sound.input"]=0.3;fact["display.level"]=0.55;fact["display.present"]=true
fact.windows_wifi_present=true;fact.windows_bluetooth_present=true
fact.windows_key_available=true;fact.windows_key_enabled=true;fact.windows_key_busy=false
fact["wifi.state"]=1;fact["bt.on"]=true
for k=0,2 do fact["windows_level_available."..k]=true end
on("set_volume",function(v)
    fact.fixture_volume_calls+=1
    fact["sound.volume"]=v
    fact["windows_level_pending.1"]=false
end)
on("chat_login",function() fact.fixture_login_calls+=1 end)
on("chat_login_open",function() fact.fixture_login_opens+=1 end)
on("chat_allow",function(index) fact.fixture_allowed=index end)
on("chat_deny",function(index) fact.fixture_denied=index end)
on("fixture_stage",function(stage)
    fact.chatting=false;fact.open=false;fact.menu_open=false
    fact["chat.signed_in"]=false;fact["chat.signing"]=false
    fact["chat.login_link"]=false;text["chat.login_help"]=""
    fact["chat.state"]="offline";fact["chat.live"]=-1
    model["chat.rows"]={}
    text["chat.input"]=""
    if stage==6 then
        fact.open=true;fact.page="none"
    elseif stage==7 then
        fact.open=true;fact.page="settings";fact.section="windows_shortcuts"
    elseif stage==0 then
        fact.chatting=true
    elseif stage==1 or stage==10 then
        fact.chatting=stage==1;fact["chat.signing"]=true;fact["chat.login_link"]=true
        if stage==10 then fact.open=true;fact.page="settings";fact.section="talk" end
        text["chat.login_hint"]="Código de ejemplo: ABCD-EFGH. No es una sesión real."
        text["chat.login_help"]="Activa el acceso con código de dispositivo en ChatGPT → Ajustes → Seguridad (o consulta al administrador). Introduce el código en el navegador y mantén este acceso abierto hasta terminar."
    elseif stage==2 then
        fact.open=true;fact.page="settings";fact.section="talk"
    elseif stage==3 then
        fact.chatting=true;fact["chat.signed_in"]=true;fact["chat.state"]="awaiting"
        model["chat.rows"]={
            {kind=1,text="Prueba de diseño: ¿puedes escribir España, café y 日本語?",detail="",state=1},
            {kind=2,text="Estos son datos de prueba para revisar las letras, las burbujas y el desplazamiento. No se ha contactado con ningún modelo ni se ha ejecutado ninguna acción.",detail="",state=1},
            {kind=4,text="Acción de ejemplo: escribir «España, café y 日本語» en una ventana de prueba.",detail="Escribir en la aplicación de prueba",state=0},
        }
    elseif stage==4 then
        fact.open=true;fact.page="settings";fact.section="menu"
    elseif stage==5 or stage==9 then
        fact.chatting=true;fact["chat.signed_in"]=true;fact["chat.state"]="idle"
        local rows={}
        for i=1,12 do rows[i]={kind=if i%2==0 then 2 else 1,text="Mensaje de ejemplo "..i..": España, café y 日本語. Un párrafo con texto suficiente para comprobar que la altura se mide y la conversación se desplaza sin superponer las líneas.",detail="",state=1} end
        model["chat.rows"]=rows
        if stage==9 then fact["chat.state"]="thinking" end
    end
end)
fact.fixture_ready=true
'''


def nodes(parts):
    for node in parts:
        yield node
        yield from nodes(node.get('nodes', node.get('children', [])))


def control_title_ready(picture):
    # Scene facts can be ready while the asynchronous font worker is still busy.
    # The center's white title is the only bright content inside this dark area.
    width,height,pixels=picture
    if width<360 or height<140:return False
    return sum(min(pixels[(y*width+x)*4:(y*width+x)*4+3])>200
        for y in range(120,140) for x in range(158,360))>=100

def retained_policy(logs, mode):
    policy=re.findall(r'retained surface policy: (\S+) · adapter: (\w+) · enabled: (true|false)',logs)
    assert policy and len(set(policy))==1, 'Missing or inconsistent native retention policy trace'
    setting,adapter,selected=policy[0]
    assert setting==mode, (setting,mode)
    enabled=mode=='1' or (mode=='auto' and adapter=='Cpu')
    assert (selected=='true')==enabled, (policy,mode)
    count=logs.count('retained surface allocated')
    assert (count>0 if enabled else count==0), 'The selected retention policy was not exercised'
    return dict(setting=setting,adapter=adapter,enabled=enabled,allocations=count)

def exercise(binary, output, root, resource_cycles=0, idle_tide_baseline=False):
    desktop = Desktop()
    scene = output / 'Marea profile ñ 海.plm'
    scene.write_text(fixture_source(root, idle_tide_baseline), encoding='utf-8')
    scene.with_suffix('.luau').write_text(FIXTURE_LOGIC, encoding='utf-8')
    env = dict(os.environ, APPDATA=str(output / 'state'), LOCALAPPDATA=str(output / 'local'),
               PLEAMAR_CONFIG=str(output / 'config'), PLEAMAR_SOCKET_DIR=f'marea-profile-ci-{os.getpid()}',
               MAREA_SEARCH_HOTKEY='', PLEAMAR_NO_RELAUNCH='1', PLEAMAR_TEST_WINDOWS='1')
    retention_mode = env.get('PLEAMAR_RETAINED_SURFACE') or 'auto'
    assert retention_mode in ('auto','0','1'), retention_mode
    env['PLEAMAR_RETAINED_SURFACE'] = retention_mode
    env.pop('PLEAMAR_FULL_REPAINT',None)
    env['PLEAMAR_TIMING'] = '1'
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    report = dict(passed=False, fixture_logic=True, fixture_background=True, environment='github-hosted', physical_input=False,
                  device_services=False, real_account=False, full_product_acceptance=False, retained_surface_mode=retention_mode,
                  idle_tide_baseline=idle_tide_baseline,
                  binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  scene_sha256=hashlib.sha256(scene.read_bytes()).hexdigest(), checks=[], images=[])
    process, hwnd = None, None

    def run(arguments):
        result = subprocess.run([str(binary), *arguments], env=env, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=15, creationflags=flags)
        with (output / 'commands.log').open('a', encoding='utf-8') as trace:
            trace.write(json.dumps(arguments, ensure_ascii=False) + '\n' + result.stdout + result.stderr)
        if result.returncode or result.stdout.lstrip().startswith('?'):
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout.strip()

    def ask(command):
        return run(['--say', scene.stem, command])

    def until(predicate, label):
        deadline, last = time.monotonic() + 40, None
        while time.monotonic() < deadline:
            if process and process.poll() is not None:
                raise RuntimeError('Scene stopped during ' + label)
            try:
                value = predicate()
                if value:
                    return value
            except (OSError, RuntimeError) as error:
                last = error
            time.sleep(.15)
        raise TimeoutError(f'{label}: {last}')

    def tree(label):
        value = json.loads(ask('describe json'))
        (output / (label + '.json')).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
        return list(nodes(value))

    def capture(label):
        picture = desktop.pixels(hwnd)
        # Reject a blank/flat surface, but retain pixels for actual visual review.
        assert len(set(picture[2][i:i + 3] for i in range(0, len(picture[2]), 16))) > 100
        path = output / (label + '.png')
        png(path, picture)
        report['images'].append(dict(file=path.name, width=picture[0], height=picture[1],
                                     sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

    try:
        run(['--check', str(scene)])
        with (output / 'scene.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([str(binary), '--scene', str(scene), '--no-hud', '--stall', '0', '--seconds', str(180 + resource_cycles * 20)], env=env,
                                       stdout=log, stderr=log, creationflags=flags)
            until(lambda: ask('get fixture_ready') == 'true', 'fixture initialization')
            hwnd = until(lambda: desktop.window(process.pid, 'pleamar surface 0 · '), 'main scene window')
            ask('emit fixture_stage 6')
            until(lambda: any(n.get('label') == 'Volumen' for n in tree('controls-tree')), 'control center')
            time.sleep(1.2)
            visible = tree('controls-tree')
            volume = next(n for n in visible if n.get('label') == 'Volumen' and n.get('role') == 'slider')
            assert volume.get('value') == '42%', volume
            assert any(n.get('checked') is True and n.get('role') == 'toggle' for n in visible)
            assert any(n.get('label') == 'Cerrar' for n in visible)
            until(lambda: control_title_ready(desktop.pixels(hwnd)), 'visible control title after font loading')
            capture('01-controls')
            # Keep both states: waiting only for the title exposed overlapping
            # card labels while their first font measurements were arriving.
            # No scene command or input should be needed to settle that layout.
            time.sleep(.75)
            capture('01-controls-resting')
            response = ask(f'drag {volume["name"]} 0 -30')
            assert 'dragged' in response, response
            assert float(ask('get fixture_volume_calls')) > 0
            assert abs(float(ask('get sound.volume')) - .42) > .05
            capture('02-volume')
            report['checks'].append('Spanish slider value/labels and named drag reaching isolated Luau')
            ask('emit fixture_stage 7')
            until(lambda: any(n.get('label') == 'Usar la tecla Windows para Marea'
                              for n in tree('shortcuts-tree')), 'shortcut page')
            key = next(n for n in tree('shortcuts-tree') if n.get('label') == 'Usar la tecla Windows para Marea')
            assert key['role'] == 'toggle' and key['checked'] is True, key
            time.sleep(1.2)
            capture('03-shortcuts')
            report['checks'].append('Translated checked Windows-key setting; no hook enabled')
            labels = ('signed-out', 'login-code', 'account-settings', 'approval-card', 'settings-menu', 'long-conversation')
            report['layout_state'] = {}
            for stage, label in enumerate(labels):
                ask(f'emit fixture_stage {stage}')
                time.sleep(1.5)
                state = {name: ask('get ' + name) for name in ('chat.rows.count', 'chat.length', 'chat.from_end', 'chat.stuck')}
                report['layout_state'][label] = state
                visible=tree(label + '-tree')
                capture(f'{stage + 4:02}-{label}')
                if stage in (0,2):
                    button=next(n for n in visible if n.get('label')=='Iniciar sesión' and n.get('role')=='button')
                    assert not button.get('covered_by'),button
                    ask('press '+button['name'])
                    until(lambda: ask('get fixture_login_calls')==('1' if stage==0 else '2'), 'login reached Luau')
                if stage==1:
                    button=next(n for n in visible if n.get('label')=='Abrir página de acceso' and n.get('role')=='button')
                    assert not button.get('covered_by'),button
                    ask('press '+button['name'])
                    until(lambda: ask('get fixture_login_opens')=='1', 'reopen reached Luau')
                if stage==3:
                    for label,key in [('Permitir','fixture_allowed'),('Esto no','fixture_denied')]:
                        button=next(n for n in visible if n.get('label')==label and n.get('role')=='button')
                        assert not button.get('covered_by'),button
                        ask('press '+button['name'])
                        until(lambda: ask('get '+key)=='2', 'approval reached the matching Luau row')
                if label == 'long-conversation':
                    assert state['chat.rows.count'] == '12', state
                    assert state['chat.stuck'] == 'true', state
                    assert float(state['chat.length']) > 404, state
                    assert abs(float(state['chat.from_end']) - 404) < 1, state
            report['checks'].append('Six native chat/settings states and long conversation keeps the visible tail')
            ask('emit fixture_stage 10')
            time.sleep(1.5)
            visible=tree('account-signing-tree')
            button=next(n for n in visible if n.get('label')=='Abrir página de acceso' and n.get('role')=='button')
            ask('press '+button['name'])
            until(lambda: ask('get fixture_login_opens')=='2', 'settings reopen reached Luau')
            capture('13-account-signing')
            report['checks'].append('Both login and reopen buttons dispatch their events on the visible monitor; no browser or account used')
            ask('emit fixture_stage 9')
            until(lambda: float(ask('get chat.stir')) > .99, 'working tide visible')
            capture('11-conversation-working')
            ask('emit fixture_stage 5')
            until(lambda: float(ask('get chat.stir')) <= .001, 'working tide faded out')
            capture('12-conversation-resting')
            report['checks'].append('Working chat tide rises and fades; both native states captured')
            if resource_cycles:
                from profile_resources import Probe, summarize
                probe = Probe(process, output / 'resources.json')
                def observe(label, seconds):
                    ask('probe start')
                    interval = probe.observe(label, seconds)
                    path = output / f'renderer-{label}.md'
                    path.write_text(ask('probe report') + '\n', encoding='utf-8')
                    interval['renderer_report'] = path.name
                    probe.save()
                    return interval
                ask('emit fixture_stage 8')
                until(lambda: ask('get open') == 'false' and ask('get chatting') == 'false', 'closed resource baseline')
                time.sleep(1.5)
                baseline = observe('closed-initial', 10)
                for cycle in range(resource_cycles):
                    ask('emit fixture_stage 5')
                    until(lambda: ask('get chat.rows.count') == '12', 'resource conversation')
                    time.sleep(1.5)
                    observe(f'conversation-{cycle}', 5)
                    ask('emit fixture_stage 8')
                    until(lambda: ask('get open') == 'false' and ask('get chatting') == 'false', 'resource closure')
                    time.sleep(1.5)
                    observe(f'closed-{cycle}', 5)
                final = observe('closed-final', 10)
                probe.report['between_closed_samples'] = summarize(baseline['final'], final['final'])
                probe.finish()
                report['resources'] = dict(file='resources.json', cycles=resource_cycles,
                    renderer_reports=True, whole_product_acceptance=False, real_sdk=False, physical_gpu_benchmark=False)
                ask('emit fixture_stage 6')
                until(lambda: any(n.get('label') == 'Volumen' for n in tree('controls-after-cycles')), 'controls after resource cycles')
                time.sleep(1.2)
                capture('10-controls-after-cycles')
                report['checks'].append('Owned renderer counters during repeated conversation/closure; final controls still render')
            assert desktop.user.PostMessageW(hwnd, 0x10, 0, 0)
            assert process.wait(timeout=20) == 0
        logs = (output / 'scene.log').read_text(encoding='utf-8')
        assert 'first frame' in logs and 'runtime error:' not in logs, logs
        report['retained_policy'] = retained_policy(logs,retention_mode)
        report['retained_surface'] = report['retained_policy']['enabled']
        report['passed'] = True
    finally:
        if process and process.poll() is None:
            if hwnd:
                desktop.user.PostMessageW(hwnd, 0x10, 0, 0)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resource-cycles', type=int, choices=range(0, 13), default=0,
                        help='Optional bounded conversation/closure resource sampling; not a whole-product benchmark')
    parser.add_argument('--idle-tide-baseline', action='store_true',
                        help='Render the pre-optimization transparent tide for a same-run comparison')
    args = parser.parse_args()
    require_ci()
    output = args.output.resolve()
    temporary = Path(os.environ['RUNNER_TEMP']).resolve()
    assert output != temporary and output.is_relative_to(temporary), 'Evidence must be in a new runner-temp directory'
    output.mkdir(parents=True, exist_ok=False)
    exercise(args.binary.resolve(strict=True), output, Path(__file__).resolve().parents[1], args.resource_cycles, args.idle_tide_baseline)


if __name__ == '__main__':
    main()
