"""Rehearse the actual tide shader on two native monitors without changing wallpaper.

Run build-desktop.py first. --hold leaves the final frame visible briefly for
window captures; no desktop input is injected. This needs a real Windows desktop.
"""
import argparse
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time
import zlib


def png(path, color):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1280, 720, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress((b'\0' + bytes(color) * 1280) * 720)) + chunk(b'IEND', b''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--hold', type=int, default=0)
    parser.add_argument('--overlay', action='store_true', help='Show the test above other apps for visual inspection')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This check requires Windows and two connected monitors.')
    binary = args.binary.resolve()
    root = Path(__file__).resolve().parents[1]
    work = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='marea-tide-'))
    work.mkdir(parents=True, exist_ok=True)
    source = (root / 'marea-desktop.plm').read_text(encoding='utf-8')
    start = source.index('    surface tide {')
    end, depth = source.index('{', start) + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    surface = source[start:end]
    if args.overlay:
        surface = surface.replace('level: bottom', 'level: overlay')
    scene = work / 'wallpaper-monitors.plm'
    prefix = '''scene WallpaperMonitors {
    surface { size: 820, 680; screens: each max 2; open: false }
    model tidepics max 2 { pic: image 1280, 720 }
    repeat k in 0..2 {
        fact windows_tide_width.$k = 0
        fact windows_tide_height.$k = 0
    }
    fact tide.on = true
    fact tide.home = 0
    prop tide.p = 1 ~0ms
    prop tide.settle = 1 ~0ms
    prop tide.fade = 1 ~0ms
    prop tide.fall = 1 ~0ms
    event splash
'''
    shader = '    shader tides = file "' + (root / 'shaders/tide.wgsl').as_posix() + '"\n'
    scene.write_text(prefix + shader + surface + '\n}', encoding='utf-8')
    pictures = [work / 'primary.png', work / 'secondary.png']
    for path, color in zip(pictures, [(30, 170, 180), (235, 140, 45)]):
        png(path, color)
    scene.with_suffix('.luau').write_text('model.tidepics = {' + ','.join(
        '{pic=' + json.dumps(path.as_posix()) + '}' for path in pictures) + '}\n', encoding='utf-8')
    env = dict(os.environ, PLEAMAR_CONFIG=str(work / 'config'), PLEAMAR_NO_RELAUNCH='1', PLEAMAR_TEST_WINDOWS='1',
               PLEAMAR_SOCKET_DIR='tide-monitors-' + str(os.getpid()))
    log_path = work / 'native.log'
    report = {'complete': False, 'physical_gui': True, 'wallpaper_changed': False}
    process = None

    def ask(command):
        return subprocess.check_output([str(binary), '--say', scene.stem, command], env=env,
            text=True, encoding='utf-8', timeout=5, creationflags=subprocess.CREATE_NO_WINDOW).strip()

    def wait(predicate):
        until = time.monotonic() + 30
        while time.monotonic() < until:
            if process.poll() is not None:
                raise RuntimeError('Native runtime exited: ' + log_path.read_text(encoding='utf-8')[-2000:])
            try:
                if predicate():
                    return
            except (subprocess.SubprocessError, ValueError):
                pass
            time.sleep(.15)
        raise RuntimeError('Native measurement/reload timed out: ' + str(log_path))

    def measure():
        return [[float(ask(f'get windows_tide_{part}.{k}')) for part in ('width', 'height')] for k in range(2)]

    try:
        with log_path.open('w', encoding='utf-8') as stream:
            process = subprocess.Popen([str(binary), '--scene', str(scene), '--no-hud', '--stall', '0'],
                cwd=work, env=env, stdout=stream, stderr=stream, creationflags=subprocess.CREATE_NO_WINDOW)
            wait(lambda: 'first frame' in log_path.read_text(encoding='utf-8'))
            assert int(ask('get screens.count')) >= 2, 'Two native monitors are required'
            wait(lambda: all(value > 0 for size in measure() for value in size))
            measured = measure()
            native = re.findall(r'surface \d+ on .+? · (\d+)×(\d+) · .+? · tide(?: copy \d+)?$',
                                log_path.read_text(encoding='utf-8'), re.MULTILINE)
            # The runtime logs each native sheet's logical size, independently of
            # the PLM properties under test. Check them after reading actual logs.
            assert [[float(w), float(h)] for w, h in native] == measured, (native, measured)
            report.update(pid=process.pid, sizes=measured, native_sheet_lines=[line for line in
                log_path.read_text(encoding='utf-8').splitlines() if 'render · surface' in line])
            for k in range(2):
                name = 'tide' if k == 0 else 'tide#screen1'
                assert [float(ask(f'get {name}.{part}')) for part in ('width', 'height')] == measured[k]
            # Inserting a new property changes IDs. Existing windows must publish
            # their measured size again even if Windows sends no resize event.
            before = log_path.read_text(encoding='utf-8').count('render · scene:')
            scene.write_text(prefix.replace('    model tidepics', '    prop inserted = 7\n    model tidepics')
                             + shader + surface + '\n}', encoding='utf-8')
            wait(lambda: log_path.read_text(encoding='utf-8').count('render · scene:') > before)
            wait(lambda: measure() == measured)
            report['after_reload'] = measure()
            # Closed Windows targets release their full-size buffers. Reopening
            # must restore them without changing the measured scene geometry.
            for _ in range(10):
                ask('fact tide.on false')
                wait(lambda: ask('get tide.on') == 'false')
                time.sleep(.12)
                ask('fact tide.on true')
                wait(lambda: ask('get tide.on') == 'true' and measure() == measured)
                time.sleep(.12)
            report['close_reopen_cycles'] = 10
            (work / 'ready.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print('READY: native tide surfaces and hot reload: ' + json.dumps(measured), flush=True)
            if args.hold:
                time.sleep(min(args.hold, 300))
            ask('quit')
            assert process.wait(timeout=15) == 0
            log = log_path.read_text(encoding='utf-8')
            assert 'runtime error' not in log and 'panicked' not in log
            report['complete'] = True
    finally:
        if process is not None and process.poll() is None:
            try:
                ask('quit')
                process.wait(timeout=10)
            except Exception:
                process.kill()
                process.wait(timeout=10)
        (work / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS: native two-monitor tide shader, independent sizes, Luau models and hot reload. ' + str(work))


if __name__ == '__main__':
    main()
