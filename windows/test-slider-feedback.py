"""Drive the real Marea renderer with a scripted drag and a slow fake device.

No OS mouse injection and no hardware settings are changed. This measures render
feedback during a held drag, complementing the native mouse/device tests.
"""
from pathlib import Path
import argparse, os, re, subprocess, tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', required=True, type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
source = (root/'marea-desktop.plm').read_text(encoding='utf-8')
for folder in ['common', 'lang', 'shaders', 'assets', 'wardrobe']:
    source = source.replace(f'"{folder}/', f'"{root.as_posix()}/{folder}/')
module = (root/'windows/level-controls.luau').read_text(encoding='utf-8')
logic = '''
local callbacks = {}
local fake = {
    watch = function(name, callback)
        callbacks[name] = callback
        callback({ volume = 1, level = 1, present = true })
    end,
    call_async = function(name, values, callback)
        after(350, function()
            if name == "audio.volume" then
                fact["sound.volume"] = values[1]
                callbacks.audio({ volume = values[1] })
            else
                fact["display.level"] = values[1]
                callbacks.brightness({ present = true, level = values[1] })
            end
            callback("", 0)
        end)
    end,
}
local install = (function()
__MODULE__
end)()
install(fake, function(message) log("test notice", message) end)
fact["sound.volume"] = 1
fact["display.level"] = 1
fact["display.present"] = true
fact.skin = "classic"
after(500, function() fact.open = true end)
'''.replace('__MODULE__', module)
with tempfile.TemporaryDirectory(prefix='marea slider feedback ñ ') as tmp:
    scene = Path(tmp)/'feedback.plm'
    scene.write_text(source, encoding='utf-8')
    scene.with_suffix('.luau').write_text(logic, encoding='utf-8')
    # Track 1 runs from y=183 to y=383 on the default main surface.
    movements = ['262,183@4200', 'down@4300']
    movements += [f'262,{183+i*4}@{4350+i*25}' for i in range(1, 41)]
    movements += ['up@5500']
    env = dict(os.environ, APPDATA=tmp, PLEAMAR_SOCKET_DIR=f'feedback-{os.getpid()}', PLEAMAR_NO_RELAUNCH='1')
    result = subprocess.run([str(args.binary.resolve()), '--scene', str(scene), '--no-hud', '--stall', '0',
        '--mouse', ' '.join(movements), '--seconds', '8', '--record',
        'windows_level_target.1,windows_level_pending.1,sound.volume'], env=env,
        capture_output=True, text=True, encoding='utf-8', timeout=75)
    output = result.stdout + result.stderr
    rows = []
    for line in result.stdout.splitlines():
        if re.fullmatch(r'[\d.]+\t[\d.-]+\t[\d.-]+\t[\d.-]+', line):
            rows.append(tuple(map(float, line.split('\t'))))
    # Scripted input waits for the first native frame. Use the observed pending
    # interval instead of assuming a fixed GPU initialization time.
    moving = [row for row in rows if row[2] == 1 and .21 < row[1] < .95]
    distinct = len({round(row[1], 2) for row in moving})
    lagging_device = sum(abs(row[1]-row[3]) > .08 for row in moving)
    assert result.returncode == 0 and 'runtime error:' not in output, output
    assert distinct >= 15 and lagging_device >= 10, f'feedback waited for the device: {distinct=} {lagging_device=}\n{output[-5000:]}'
    final = rows[-1]
    assert abs(final[1]-.2) < .03 and abs(final[3]-final[1]) < .015 and final[2] == 0, final
    print(f'PASS: {distinct} intermediate slider positions while the device lagged in {lagging_device} frames; final value confirmed.')
