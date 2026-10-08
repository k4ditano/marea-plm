"""Exercise Marea's real Luau adapter and real worker with no display surface."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--worker', type=Path, required=True)
args = parser.parse_args()
binary, worker = args.binary.resolve(), args.worker.resolve()
module = Path(__file__).with_name('deriva-worker.luau').read_text(encoding='utf-8')
with tempfile.TemporaryDirectory(prefix='marea deriva runtime ñ ') as temporary:
    root = Path(temporary)
    scene = root / 'deriva-runtime.plm'
    scene.write_text('''scene DerivaRuntime {
        permissions { run: "deriva-worker" }
        surface { size: 120, 80 }
        fact done = false
        text result = ""
    }''', encoding='utf-8')
    scene.with_suffix('.luau').write_text('local install = (function()\n' + module + r'''
end)()
local invoke = install(run)
invoke({"where"}, function(where, error)
    assert(where, error)
    invoke({"ingest", "--request", json.encode({type="text", text="Bahía de León 海", title="Luau native"})}, function(saved, error)
        assert(saved and saved.saved == 1, error or "save did not persist")
        invoke({"list", "--limit", "60"}, function(items, error)
            assert(items and #items.items == 1 and items.items[1].title == "Luau native", error or "list mismatch")
            invoke({"search", "--query", "bahia", "--limit", "60"}, function(found, error)
                assert(found and #found.items == 1, error or "search mismatch")
                text.result = "PASS real Luau and SQLite 海"
                fact.done = true
            end)
        end)
    end)
end)
''', encoding='utf-8')
    env = dict(os.environ, MAREA_DERIVA_DIR=str(root / 'library 海'),
        PLEAMAR_CONFIG=str(root / 'config'), PLEAMAR_SOCKET_DIR=f'deriva-runtime-{os.getpid()}',
        PLEAMAR_NO_RELAUNCH='1', PATH=str(worker.parent) + os.pathsep + os.environ.get('PATH', ''))
    log = root / 'runtime.log'
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.Popen([str(binary), '--scene', str(scene), '--screen', f'absent-deriva-{os.getpid()}',
            '--no-hud', '--stall', '0', '--seconds', '25'], cwd=root, env=env,
            stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        def ask(command):
            return subprocess.run([str(binary), '--say', scene.stem, command], env=env,
                capture_output=True, encoding='utf-8', timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                reply = ask('get done')
                if reply.returncode == 0 and reply.stdout.strip() == 'true': break
                assert process.poll() is None, log.read_text(encoding='utf-8')
                time.sleep(.1)
            else: raise AssertionError(log.read_text(encoding='utf-8'))
            assert ask('get result').stdout.strip() == 'PASS real Luau and SQLite 海'
            assert ask('quit').returncode == 0
            assert process.wait(timeout=10) == 0
            content = log.read_text(encoding='utf-8')
            assert 'waiting for one to appear' in content and 'first frame' not in content
            assert 'runtime error' not in content and 'panicked' not in content, content
        finally:
            if process.poll() is None: process.kill(); process.wait(timeout=10)
print('PASS: real native Luau adapter launches bundled Deriva, ingests, lists and searches SQLite with Unicode; no graphical validation')
