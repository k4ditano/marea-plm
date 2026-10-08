"""Exercise Marea's actual asynchronous file search on isolated Unicode paths."""
from pathlib import Path
import argparse, json, os, subprocess, tempfile, time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', required=True, type=Path)
args = parser.parse_args()
binary = str(args.binary.resolve())
root = Path(__file__).resolve().parents[1]
source = (root/'marea-desktop.plm').read_text(encoding='utf-8')
for folder in ['common', 'lang', 'shaders', 'assets', 'wardrobe']:
    source = source.replace(f'"{folder}/', f'"{root.as_posix()}/{folder}/')
source = source.replace('scene Marea {', 'scene Marea {\n    fact search_found = false\n    fact search_stale = false')
logic = (root/'marea-desktop.luau').read_text(encoding='utf-8') + '''
every(50, function()
    local found, stale = false, false
    for _, row in ipairs(model.results or {}) do
        if row.name == "Canción búsqueda [2026].txt" and row.filepath then found = true end
        if row.name == "previous query.txt" then stale = true end
    end
    fact.search_found = found
    fact.search_stale = stale
end)
'''
with tempfile.TemporaryDirectory(prefix='Marea búsqueda ñ ') as tmp:
    home = Path(tmp)/'User with spaces'
    home.mkdir()
    (home/'Canción búsqueda [2026].txt').write_text('Test fixture, no personal data.', encoding='utf-8')
    (home/'previous query.txt').write_text('Test fixture.', encoding='utf-8')
    scene = Path(tmp)/'search.plm'
    scene.write_text(source, encoding='utf-8')
    # Choose the search root without pretending this is a different Windows
    # account (USERPROFILE also influences native graphics/shell components).
    logic = logic.replace('local home_dir = sys.ask("env", "HOME") or "."',
                          'local home_dir = '+json.dumps(home.as_posix(), ensure_ascii=False))
    scene.with_suffix('.luau').write_text(logic, encoding='utf-8')
    env = dict(os.environ, APPDATA=tmp, MAREA_SEARCH_HOTKEY='',
               PLEAMAR_SOCKET_DIR=f'search-{os.getpid()}', PLEAMAR_NO_RELAUNCH='1')
    with (Path(tmp)/'run.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([binary, '--scene', str(scene), '--no-hud', '--stall', '0'],
                                   env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        def ask(command):
            return subprocess.check_output([binary, '--say', scene.stem, command], env=env,
                stderr=subprocess.DEVNULL, text=True, encoding='utf-8', timeout=10).strip()
        def expect(name, value):
            until = time.monotonic()+20
            while time.monotonic() < until:
                try:
                    if ask('get '+name) == value: return
                except subprocess.SubprocessError: pass
                if process.poll() is not None: break
                time.sleep(.1)
            log.flush()
            raise AssertionError((Path(tmp)/'run.log').read_text(encoding='utf-8'))
        try:
            expect('demo', 'false')
            until = time.monotonic()+20
            while not ask('get screen.0.name').startswith('\\\\.'):
                if time.monotonic() >= until:
                    log.flush()
                    raise AssertionError('GPU surface did not become ready\n'+(Path(tmp)/'run.log').read_text(encoding='utf-8'))
                time.sleep(.1)
            time.sleep(1)
            ask('emit search')
            expect('searching', 'true')
            ask('text query previous')
            ask('text query busqueda cancion')
            expect('search_found', 'true')
            expect('search_stale', 'false')
            ask('text query cancionn')
            expect('search_found', 'true')
            time.sleep(.5)
            log.flush()
            output = (Path(tmp)/'run.log').read_text(encoding='utf-8')
            assert 'runtime error:' not in output, output
            print('PASS: actual Marea search, accent folding, word order, typo, Unicode and spaces, stale query discarded, no external search helper.')
        finally:
            if process.poll() is None:
                try:
                    ask('quit')
                    process.wait(timeout=15)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
