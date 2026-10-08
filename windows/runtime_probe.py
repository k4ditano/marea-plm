"""Check an actual native x64 pleamar executable and its Luau runtime without a window."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import uuid


def check_runtime(binary):
    binary = Path(binary).resolve(strict=True)
    if os.name != 'nt': raise RuntimeError('The desktop installer requires Windows.')
    with binary.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ': raise RuntimeError('Expected a native Windows executable.')
        stream.seek(struct.unpack_from('<I', header, 60)[0])
        pe = stream.read(6)
        if len(pe) != 6 or pe[:4] != b'PE\0\0' or struct.unpack_from('<H', pe, 4)[0] != 0x8664:
            raise RuntimeError('Marea requires the Windows x64 pleamar build.')
    temporary_root = Path(tempfile.gettempdir()).resolve()
    with tempfile.TemporaryDirectory(prefix='marea runtime ñ ', dir=temporary_root) as temporary:
        folder = Path(temporary).resolve()
        assert folder.parent == temporary_root and folder.name.startswith('marea runtime ñ ')
        scene = folder / 'runtime.plm'
        marker = 'MAREA_LUAU_READY_' + uuid.uuid4().hex
        scene.write_text('scene Runtime { surface { kind: window; size: 40, 40 } fact ready = false }', encoding='utf-8')
        scene.with_suffix('.luau').write_text('assert(type(sys.watch) == "function")\nfact.ready = true\n'
            f'log("{marker}")\n', encoding='utf-8')
        environment = dict(os.environ, APPDATA=str(folder / 'state'), PLEAMAR_NO_RELAUNCH='1',
            PLEAMAR_SOCKET_DIR='marea-runtime-' + uuid.uuid4().hex)
        try:
            result = subprocess.run([str(binary), '--scene', str(scene), '--screen', 'marea-runtime-absent-output',
                '--no-hud', '--stall', '0', '--seconds', '2'], cwd=folder, env=environment,
                capture_output=True, encoding='utf-8', errors='replace', timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('pleamar did not finish the native Luau runtime check within 30 seconds.') from error
        if result.returncode:
            detail = (result.stderr + '\n' + result.stdout).strip()[-3000:]
            raise RuntimeError(f'pleamar could not run the native runtime check (exit {result.returncode}):\n{detail}')
        if f'luau   · {marker}' not in result.stdout.splitlines():
            raise RuntimeError('pleamar did not execute Luau. Build it with default features; a --no-default-features executable cannot run Marea.')
        if 'first frame' in result.stdout + result.stderr:
            raise RuntimeError('The runtime did not honor the absent-output check.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    args = parser.parse_args()
    try: check_runtime(args.binary)
    except (OSError, RuntimeError) as error:
        parser.exit(1, f'Native runtime check failed: {error}\n')
    print('PASS: native Windows x64 runtime executed Luau and exited; no display selected')


if __name__ == '__main__': main()
