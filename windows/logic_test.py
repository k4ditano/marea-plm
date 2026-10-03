"""Shared runner for isolated Luau assertions; native services are mocked."""
from pathlib import Path
import os
import subprocess
import tempfile


def runner_arguments(parser):
    runner = parser.add_mutually_exclusive_group(required=True)
    runner.add_argument('--luau-runner', type=Path, help='pleamar luau-test executable: no windows or GPU')
    runner.add_argument('--binary', type=Path, help='full pleamar runtime (opens a test window)')


def run_checks(args, checks, marker, label):
    with tempfile.TemporaryDirectory(prefix=f'marea {label} ñ ') as tmp:
        logic = Path(tmp) / 'regression.luau'
        logic.write_text(checks, encoding='utf-8')
        env = dict(os.environ, APPDATA=tmp, PLEAMAR_SOCKET_DIR=f'logic-{os.getpid()}', PLEAMAR_NO_RELAUNCH='1')
        if args.luau_runner:
            command = [str(args.luau_runner.resolve()), str(logic)]
        else:
            scene = logic.with_suffix('.plm')
            scene.write_text('scene Regression { surface { kind: window; size: 160, 80 } }', encoding='utf-8')
            command = [str(args.binary.resolve()), '--scene', str(scene), '--no-hud', '--stall', '0', '--seconds', '3']
        result = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf-8', timeout=45,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        output = result.stdout + result.stderr
        assert result.returncode == 0 and marker in output and 'runtime error:' not in output, output
        print(next(line for line in output.splitlines() if marker in line))
