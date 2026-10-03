"""Render/drag the real media volume row against an owned silent Windows player.

Uses pleamar's scripted input, never moves the desktop pointer or changes the
master output volume. The fixture is launched without taking keyboard focus.
"""
from pathlib import Path
import argparse, json, os, subprocess, tempfile, time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--fixture', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
binary, fixture = args.binary.resolve(), args.fixture.resolve()
with tempfile.TemporaryDirectory(prefix='marea media volume ñ ') as tmp:
    work = Path(tmp)
    scene = work / 'media-volume.plm'
    scene.write_text('import ' + json.dumps((root / 'common/palette.plm').as_posix()) + '\nscene MediaVolumeTest {\n'
        'surface { kind: window; size: 496, 190 }\npermissions { services: "media", "media.*" }\n'
        'let x0 = 20\nlet card.x = 248\nlet by = 100\nprop content = 1\n'
        'box {from: 0, 0; size: 496, 190; color: #151515}\nfact verified = false\nfact failed = false\n'
        + (root / 'windows/media-volume.plm').read_text(encoding='utf-8')
        + (root / 'windows/media-volume-row.plm').read_text(encoding='utf-8') + '\n}', encoding='utf-8')
    env = dict(os.environ, APPDATA=str(work / 'state'), PLEAMAR_SOCKET_DIR='owned-media-volume', PLEAMAR_NO_RELAUNCH='1')
    with (work / 'player.log').open('w', encoding='utf-8') as player_log:
        player = subprocess.Popen([str(fixture), '--audio'], stdout=player_log, stderr=player_log,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            time.sleep(1)
            assert player.poll() is None, (work / 'player.log').read_text(encoding='utf-8')
            expected = f'org.pleamar.validation.media.{player.pid}'
            logic = 'local expected = ' + json.dumps(expected) + '\n'
            logic += 'local install = (function()\n' + (root / 'windows/media-volume.luau').read_text(encoding='utf-8') + '\nend)()\n'
            logic += '''
local function notice(error) fact.failed = true; log(error) end
local observe = install(sys, notice)
local changed = 0
sys.watch("media", function(value)
    if value.player == expected then observe(value) else observe({}) end
end)
on("windows_set_media_volume", function() changed += 1 end)
after(6500, function()
    sys.ask_async("media.state", {}, function(value, error)
        assert(not error and value.player == expected, "owned player changed")
        assert(value.can_volume and math.abs(value.volume - 0.7) < 0.015, "drag did not apply 70%")
        assert(changed >= 3, "the actual generated track did not receive press/drag/release")
        fact.verified = true
        log("PASS: native media volume track receives press/drag/release and confirms 70% in Core Audio")
    end)
end)
'''
            scene.with_suffix('.luau').write_text(logic, encoding='utf-8')
            result = subprocess.run([str(binary), '--scene', str(scene), '--no-hud', '--stall', '0', '--seconds', '9',
                '--mouse', '214,132@2800 down@3000 270,132@3200 350,132@3400 up@3700', '--record', 'verified,failed'],
                env=env, capture_output=True, text=True, encoding='utf-8', timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.stdout + result.stderr
            assert result.returncode == 0 and 'PASS: native media volume track' in output and 'runtime error:' not in output, output[-5000:]
            assert not any(line.endswith('\ttrue') for line in output.splitlines() if '\t' in line), output[-2000:]
            print(next(line for line in output.splitlines() if 'PASS: native media volume track' in line))
        finally:
            player.terminate()
            player.wait(timeout=10)
