"""Rehearse the generated card/scroll zones in a native window, without moving the desktop mouse."""
import argparse, os, re, subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
marea = Path(__file__).resolve().parents[1]
binary = args.binary.resolve(strict=True)
work = args.output.resolve()
work.mkdir(parents=True, exist_ok=False)
source = (marea / 'marea-desktop.plm').read_text(encoding='utf-8')
card = source[source.index('            component DriftCard'):source.index('            // ── the wardrobe')]
model = re.search(r'    model drift max 4 \{[^\n]+', source)[0]
scene = work / 'deriva-card-window.plm'
scene.write_text('import "' + (marea / 'common/palette.plm').as_posix() + '"\n' + '''scene DerivaCardTest {
    surface { kind: window; size: 496, 540 }
    event drift_pick ->
    event drift_scroll ->
    event drift_open ->
    fact page: none | drift = drift
    prop paging = 1
    fact drift.missing = false
    fact drift.kept = 1
    fact windows_deriva_loaded = true
    fact windows_deriva_busy = false
    fact clicks = 0
    fact wheels = 0
    text opened = ""
    text drift_q = ""
    text windows_deriva_status = ""
    let card.x = 248
    let card.y = 210
    let card.top = 0
''' + model + '\n' + card + '\n}', encoding='utf-8')
scene.with_suffix('.luau').write_text('''model.drift = {{title="YouTube native click test", source="youtube", kind="VIDEO", date="Today",
    preview="", has_preview=false, link="https://www.youtube.com/watch?v=dQw4w9WgXcQ"}}
on("drift_pick", function(i)
    assert(i == 0, "An unused model slot received a click")
    fact.clicks += 1
    text.opened = model.drift[i + 1].link
end)
on("drift_scroll", function() fact.wheels += 1 end)
''', encoding='utf-8')
env = dict(os.environ, PLEAMAR_CONFIG=str(work/'config'), PLEAMAR_SOCKET_DIR='deriva-card-test',
    PLEAMAR_NO_RELAUNCH='1', PLEAMAR_DEBUG_ZONES='1')
log = work / 'native.log'
with log.open('w',encoding='utf-8') as output:
    process = subprocess.Popen([str(binary),'--scene',str(scene),'--no-hud','--stall','0',
        '--seconds','9','--mouse','360,220@1000 click@1300 125,220@2000 click@2300 wheel-@2800',
        '--record','clicks,wheels,opened'], cwd=work,env=env,stdout=output,stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        assert process.wait(timeout=30) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
content = log.read_text(encoding='utf-8')
assert 'first frame' in content, content[-4000:]
assert 'runtime error' not in content and 'panicked' not in content, content[-4000:]
rows = [line.split('\t') for line in content.splitlines() if '\t' in line]
assert any(len(row) == 4 and row[1:3] == ['1.0000','1.0000'] and row[3].endswith('dQw4w9WgXcQ') for row in rows), content[-1500:]
assert not any(len(row) == 4 and row[1] not in ['0.0000','1.0000','clicks'] for row in rows), rows[-10:]
print('PASS: native GPU window: empty slot ignores click, actual generated card emits original URL once, scrolling over card still works. No desktop mouse movement or browser launch.')
