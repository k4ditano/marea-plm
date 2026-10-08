"""Exercise the generated profile on a real Windows desktop using isolated state."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', required=True, type=Path)
parser.add_argument('--hold-deriva', type=int, default=0, help='Seconds allowed to click the native Deriva retry button (maximum 180)')
args = parser.parse_args()
binary = str(args.binary.resolve())
root = Path(__file__).resolve().parents[1]
scene = root / 'marea-desktop.plm'
subprocess.run([binary, '--check', str(scene)], check=True)
with tempfile.TemporaryDirectory(prefix='marea Windows ñ ') as tmp:
    sessions = Path(tmp) / 'codex data' / 'sessions'
    sessions.mkdir(parents=True)
    claude = Path(tmp) / 'claude data'
    claude.mkdir()
    # An explicit, empty provider config prevents fallback to a user's account.
    # Keep the real profile/GPU cache; isolating quota input must not reset it.
    (claude / '.claude.json').write_text('null', encoding='utf-8')
    (sessions / 'rollout-fixture.jsonl').write_text(json.dumps({
        'type': 'event_msg', 'timestamp': time.time(),
        'payload': {'type': 'token_count', 'rate_limits': {'limit_id': 'codex', 'plan_type': 'pro',
            'primary': {'used_percent': 27, 'window_minutes': 10080, 'resets_at': time.time() + 3600}}}
    }), encoding='utf-8')
    env = dict(os.environ, APPDATA=tmp, PLEAMAR_SOCKET_DIR=f'marea-test-{os.getpid()}',
               CODEX_HOME=str(sessions.parent), CLAUDE_CONFIG_DIR=str(claude),
               PLEAMAR_NO_RELAUNCH='1', MAREA_SEARCH_HOTKEY='', LANG='es_ES.UTF-8', LC_ALL='C.UTF-8')
    if args.hold_deriva:
        env['PLEAMAR_TEST_WINDOWS'] = '1'
    with open(Path(tmp) / 'run.log', 'w', encoding='utf-8') as log:
        process = subprocess.Popen([binary, '--scene', str(scene), '--no-hud', '--stall', '0'],
                                   env=env, cwd=tmp, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        def ask(command):
            return subprocess.check_output([binary, '--say', scene.stem, command], env=env,
                                           stderr=subprocess.DEVNULL, text=True, timeout=10).strip()

        def expect(name, value, seconds=15):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                try:
                    actual = ask(f'get {name}')
                    if actual == value:
                        return
                except subprocess.SubprocessError:
                    actual = 'pipe unavailable'
                if process.poll() is not None:
                    break
                time.sleep(.1)
            raise AssertionError(f'{name}: expected {value}, received {actual}')

        try:
            expect('windows_initialized', 'true', seconds=45)
            expect('locale', 'es')
            # IPC/Lua can be ready before the first GPU surface is published.
            deadline = time.monotonic() + 15
            while not ask('get screen.0.name').startswith('\\\\.'):
                if time.monotonic() >= deadline:
                    raise AssertionError('first monitor was not published')
                time.sleep(.1)
            time.sleep(1)
            expect('skin', 'classic')
            expect('demo', 'false')
            # Native run() must resolve the packaged helper against the logic
            # file even when the caller starts in a different Unicode directory.
            expect('ag.kind.1', '2')
            expect('ag.used.1.1', '27')
            expect('ag.worst', '73')
            for event in ['record', 'record_toggle']:
                print(f'Checking {event}', flush=True)
                ask(f'emit {event}')
                expect('face', 'count')
                expect('taping', 'false')
                ask('emit stop')
                expect('face', 'eye')
                expect('taping', 'false')
                expect('windows_recording_busy', 'false')
            if shutil.which('deriva-worker') is None:
                ask('emit show_drift')
                expect('page', 'drift')
                expect('windows_deriva_busy', 'false')
                expect('windows_deriva_loaded', 'false')
                expect('windows_deriva_status', 'Deriva no pudo ejecutar deriva-worker. Comprueba su instalacion nativa para Windows y PATH.')
                ask('text drift_q missing worker retry')
                time.sleep(.5)
                expect('windows_deriva_busy', 'false')
                assert 'PATH' in ask('get windows_deriva_status')
                ask('emit drift_open')
                expect('windows_deriva_busy', 'false')
                print('PASS: native missing Deriva process, visible failure state and query/refresh retry (no storage validation)', flush=True)
                if args.hold_deriva:
                    ask('text windows_deriva_status Pulsa Actualizar para comprobar el reintento.')
                    print(f'Inspection process={process.pid}; socket={env["PLEAMAR_SOCKET_DIR"]}; APPDATA={tmp}', flush=True)
                    expect('windows_deriva_status', 'Deriva no pudo ejecutar deriva-worker. Comprueba su instalacion nativa para Windows y PATH.',
                           seconds=max(1, min(args.hold_deriva, 180)))
                    print('PASS: visible Deriva retry button replaced the test marker with the actual native process failure', flush=True)
                    time.sleep(2)
            # Cancelling the countdown must not start a delayed recording.
            time.sleep(4)
            expect('face', 'eye')
            expect('taping', 'false')
            log.flush()
            output = (Path(tmp) / 'run.log').read_text(encoding='utf-8')
            assert 'runtime error:' not in output, output
            print('PASS: native profile, Luau, Spanish locale, Classic skin, isolated quota helper from Unicode cwd, countdown cancellation and no fake notifications.')
        except Exception:
            log.flush()
            print((Path(tmp) / 'run.log').read_text(encoding='utf-8'))
            raise
        finally:
            if process.poll() is None:
                try:
                    ask('quit')
                    process.wait(timeout=15)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=10)
