"""Generate and check the desktop profile without creating any native windows."""
from pathlib import Path
import argparse
import subprocess
import sys

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
run(binary, '--check', root / 'marea-desktop.plm')
run(runner, '--compile-only', root / 'marea-desktop.luau')
for name in ['level-controls', 'device-controls', 'wallpapers', 'screenshots', 'window-shelf', 'recording', 'notifications', 'tray', 'agent-reader', 'calendar-reminders', 'deriva', 'media-controls', 'media-volume', 'desktop-controls', 'weather']:
    run(sys.executable, root / f'windows/test-{name}.py', '--luau-runner', runner)
print('PASS: generated PLM/Luau and fifteen isolated logic suites; no desktop or hardware validation')
