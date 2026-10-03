"""Reject a real no-Luau executable even though it can compile Marea's scene."""
import argparse
from pathlib import Path
import subprocess
from runtime_probe import check_runtime


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--without-luau', type=Path, required=True)
args = parser.parse_args()
scene = Path(__file__).resolve().parents[1] / 'marea-desktop.plm'
syntax = subprocess.run([str(args.without_luau.resolve()), '--check', str(scene)], capture_output=True,
    encoding='utf-8', errors='replace', timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
assert syntax.returncode == 0, 'The negative executable must first pass scene syntax: ' + syntax.stderr
try:
    check_runtime(args.without_luau)
except RuntimeError as error:
    assert 'did not execute Luau' in str(error), str(error)
else:
    raise AssertionError('A real executable without Luau was accepted')
check_runtime(args.binary)
print('PASS: syntax-only no-Luau executable rejected; native default-Luau executable accepted')
