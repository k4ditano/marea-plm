"""Capture the actual Marea chat/settings layout with explicit fixture data.

Uses native DX12 surfaces on non-primary DISPLAY2 and WGC of only the child
scene. No real account, model request, desktop input or system mutation occurs.
This is visual/layout evidence, not end-to-end chat or input acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--harness', type=Path, required=True, help='pleamar library test executable')
    parser.add_argument('--output', type=Path, required=True, help='new evidence directory')
    args = parser.parse_args()
    assert os.name == 'nt'
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    scene = output / 'chat-layout.plm'
    source = (root / 'marea-desktop.plm').read_text(encoding='utf-8')
    for folder in ('common', 'lang', 'shaders', 'assets', 'wardrobe'):
        source = source.replace('"' + folder + '/', '"' + (root / folder).as_posix() + '/')
    source = re.sub(r'keyboard: on_demand[^\n]*', 'keyboard: none', source)
    source = source.replace('reserve: 72 while taking_room', 'reserve: 0')
    source = source.replace('scene Marea {', 'scene ChatLayout {\n event fixture_stage ->\n fact fixture_ready = false\n', 1)
    # Only this bounded fixture logic accompanies the real generated UI. No
    # Marea external worker, notification/radio command or account reader runs.
    scene.write_text(source, encoding='utf-8')
    scene.with_suffix('.luau').write_text(r'''
fact.locale="es"
fact.hidden=false;fact.needed=true;fact.home=0
fact["hosts.0"]=true;fact["hosts.1"]=false
on("fixture_stage",function(stage)
    fact.chatting=false;fact.open=false;fact.menu_open=false
    fact["chat.signed_in"]=false;fact["chat.signing"]=false
    fact["chat.state"]="offline";fact["chat.live"]=-1
    model["chat.rows"]={}
    text["chat.input"]=""
    if stage==0 then
        fact.chatting=true
    elseif stage==1 then
        fact.chatting=true;fact["chat.signing"]=true
        text["chat.login_hint"]="Código de ejemplo: ABCD-EFGH. No es una sesión real."
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
    elseif stage==5 then
        fact.chatting=true;fact["chat.signed_in"]=true;fact["chat.state"]="idle"
        local rows={}
        for i=1,12 do rows[i]={kind=if i%2==0 then 2 else 1,text="Mensaje de ejemplo "..i..": España, café y 日本語. Un párrafo con texto suficiente para comprobar que la altura se mide y la conversación se desplaza sin superponer las líneas.",detail="",state=1} end
        model["chat.rows"]=rows
    end
end)
fact.fixture_ready=true
''', encoding='utf-8')
    env = dict(os.environ, APPDATA=str(output / 'state'), LOCALAPPDATA=str(output / 'local'),
               PLEAMAR_SOCKET_DIR=f'chat-layout-{os.getpid()}', MAREA_SEARCH_HOTKEY='',
               PLEAMAR_NO_RELAUNCH='1', PLEAMAR_SCENE_TEST_BINARY=str(args.binary.resolve()),
               PLEAMAR_SCENE_TEST_FILE=str(scene), PLEAMAR_SCENE_TEST_OUTPUT=str(output))
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    report = {'complete': False, 'fixture_data': True, 'real_model': False, 'physical_input': False, 'images': [],
              'binary_sha256': hashlib.sha256(args.binary.read_bytes()).hexdigest(),
              'scene_sha256': hashlib.sha256(scene.read_bytes()).hexdigest()}

    def ask(command):
        return subprocess.check_output([str(args.binary.resolve()), '--say', scene.stem, command],
            env=env, encoding='utf-8', stderr=subprocess.DEVNULL, timeout=5, creationflags=flags).strip()

    def until(predicate, label):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            assert process.poll() is None, f'Native capture fixture stopped during {label}'
            try:
                if predicate(): return
            except (subprocess.SubprocessError, OSError): pass
            time.sleep(.1)
        raise TimeoutError(label)

    with (output / 'harness.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([str(args.harness.resolve()), '--ignored', '--exact',
            'platform::windows_desktop::scene_tests::native_scene_capture', '--nocapture'],
            env=env, stdout=log, stderr=log, creationflags=flags)
        try:
            until(lambda: ask('get fixture_ready') == 'true', 'fixture initialization')
            for stage, label in enumerate(('signed-out', 'login-code', 'account-settings', 'approval-card', 'settings-menu', 'long-conversation')):
                ask(f'emit fixture_stage {stage}')
                time.sleep(1.2)
                report.setdefault('layout_state', {})[label] = {name: ask('get ' + name)
                    for name in ('chat.rows.count', 'chat.length', 'chat.from_end', 'chat.stuck')}
                (output / 'request').write_text(label, encoding='utf-8')
                until(lambda: (output / 'captured').read_text() == label, label)
                report['images'].append(str(output / (label + '.png')))
                if label == 'long-conversation':
                    state = report['layout_state'][label]
                    assert state['chat.stuck'] == 'true', 'Layout reflow released the chat tail without user input'
                    assert abs(float(state['chat.from_end']) - 404) < 1, 'The last chat row is below the viewport'
            (output / 'request').write_text('quit')
            assert process.wait(timeout=20) == 0
            report['native'] = json.loads((output / 'capture-result.json').read_text())
            assert 'first frame' in (output / 'scene.log').read_text(encoding='utf-8')
            assert 'runtime error:' not in (output / 'scene.log').read_text(encoding='utf-8')
            report['complete'] = True
        finally:
            if process.poll() is None:
                (output / 'request').write_text('quit')
                try: process.wait(timeout=20)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
            (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: six native Marea layout captures produced; visual inspection and real account/input validation are separate.')
    print(output)


if __name__ == '__main__': main()
