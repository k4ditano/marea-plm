"""Generate and check the desktop profile without creating any native windows."""
from pathlib import Path
import argparse
import subprocess
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True, help='pleamar, used only for --check')
parser.add_argument('--luau-runner', type=Path, required=True, help='pleamar luau-test example')
args = parser.parse_args()
binary, runner = args.binary.resolve(), args.luau_runner.resolve()


def run(*command):
    result = subprocess.run(list(map(str, command)), cwd=root, timeout=60,
                            capture_output=True, text=True, encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.stdout: print(result.stdout, end='')
    if result.stderr: print(result.stderr, end='', file=sys.stderr)
    result.check_returncode()


run(sys.executable, root / 'windows/build-desktop.py')
run(sys.executable, root / 'windows/test-profile-source.py')
scene = (root / 'marea-desktop.plm').read_text(encoding='utf-8')
for event in ['chat_login', 'chat_login_cancel', 'chat_login_open']:
    assert re.search(r'\bevent\s+' + event + r'\s+->', scene), f'{event} must reach its Luau handler'
settings = scene.split('pages section {', 1)[1].split("// ── the agents' reservoirs", 1)[0]
assert re.findall(r'page (\w+) "[^"]+" \{', settings) == [
    'menu', 'home', 'look', 'language', 'lock', 'notices', 'talk', 'tasks', 'keys', 'memory', 'windows_shortcuts']
assert '"What she remembers", "Keyboard shortcuts") { at: px0' in scene
run(binary, '--check', root / 'marea-desktop.plm')
run(runner, '--compile-only', root / 'marea-desktop.luau')
run(binary, '--check', root / 'tools/windows-overview.plm')
run(runner, '--compile-only', root / 'tools/windows-overview.luau')
run(binary, '--check', root / 'tools/windows-dock.plm')
run(runner, '--compile-only', root / 'tools/windows-dock.luau')
for name in ['level-controls', 'app-audio', 'device-controls', 'wallpapers', 'screenshots', 'window-shelf', 'recording', 'notifications', 'tray', 'agent-reader', 'calendar-reminders', 'deriva', 'deriva-library', 'deriva-search', 'media-controls', 'media-volume', 'desktop-controls', 'weather', 'startup', 'menu-language', 'software', 'chat', 'chat-memory', 'desktop-agent', 'window-manager']:
    run(sys.executable, root / f'windows/test-{name}.py', '--luau-runner', runner)
run(sys.executable, root / 'windows/test-window-overview.py', '--luau-runner', runner)
run(sys.executable, root / 'windows/test-window-dock.py', '--luau-runner', runner)
run(sys.executable, root / 'windows/test-sound-profile.py', '--luau-runner', runner)
run(sys.executable, root / 'windows/test-display-routing.py', '--luau-runner', runner)
run(sys.executable, root / 'windows/test-auto-hide.py', '--luau-runner', runner)
run(sys.executable, root / 'windows/test-shortcuts.py', '--luau-runner', runner)
run(sys.executable, root / 'windows/test-chat-credentials.py', '--luau-runner', runner)
run(sys.executable, root / 'windows/test-chat-tasks.py', '--luau-runner', runner)
run(sys.executable, root / 'windows/test-task-notices.py', '--luau-runner', runner)
print('PASS: generated PLM/Luau, native overview source and isolated logic suites; no desktop or hardware validation')
