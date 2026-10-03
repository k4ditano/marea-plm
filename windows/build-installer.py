"""Build an offline, per-user x64 setup from tested native binaries and pinned tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
APP_ID = 'A8D741A8-45D5-4DE8-A38E-27DA65D253F8'
NODE_VERSION = 'v22.23.3'

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def run(*args, cwd=ROOT):
    result = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True,
        encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)
    result.check_returncode()

def x64(path):
    with path.open('rb') as stream:
        header = stream.read(64)
        if len(header) < 64 or header[:2] != b'MZ': raise ValueError(f'Not a PE image: {path.name}')
        stream.seek(struct.unpack_from('<I', header, 60)[0])
        if stream.read(6) != b'PE\0\0\x64\x86': raise ValueError(f'Not native Windows x64: {path.name}')

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['pleamar-binary', 'worker', 'node-directory', 'crt-directory', 'iscc', 'output']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--version', required=True, help='For example 0.2.8-preview.1')
    p.add_argument('--engine-source', required=True, help='Engine source commit/ref recorded in release metadata')
    args = p.parse_args()
    if os.name != 'nt': p.error('Build the Windows installer on Windows.')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-preview\.\d+)?', args.version): p.error('Invalid version.')
    if not re.fullmatch(r'[A-Za-z0-9._/+\-]{1,100}', args.engine_source): p.error('Invalid engine source ref.')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    stage = out / 'payload'
    stage.mkdir(exist_ok=False)

    def copy(source, relative):
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir(): shutil.copytree(source, target)
        else: shutil.copy2(source, target)

    engine, worker = args.pleamar_binary.resolve(strict=True), args.worker.resolve(strict=True)
    run(sys.executable, ROOT / 'windows/build-desktop.py')
    for source, name in [(engine, 'pleamar.exe'), (worker, 'deriva-worker.exe'), (args.node_directory / 'node.exe', 'node.exe')]:
        x64(source)
        copy(source, 'bin/' + name)
    node_version = subprocess.check_output([str(stage / 'bin/node.exe'), '--version'], creationflags=subprocess.CREATE_NO_WINDOW).decode().strip()
    if node_version != NODE_VERSION: raise ValueError(f'Expected Node {NODE_VERSION}, found {node_version}')
    copy(args.node_directory / 'LICENSE', 'bin/licenses/node/LICENSE')
    compiler = json.loads((engine.parent / 'dxc-runtime.json').read_text(encoding='utf-8-sig'))
    expected = {'dxcompiler.dll','dxil.dll','licenses/dxc/LICENCE-MIT.txt','licenses/dxc/LICENSE-LLVM.txt','licenses/dxc/LICENSE-MS.txt'}
    if set(compiler['files']) != expected: raise ValueError('Incomplete shader compiler manifest.')
    for relative, sha in compiler['files'].items():
        source = engine.parent / relative
        if digest(source) != sha.lower(): raise ValueError('Changed shader compiler file: ' + relative)
        copy(source, 'bin/' + relative)
    copy(engine.parent / 'dxc-runtime.json', 'bin/dxc-runtime.json')
    # Only the licensed x64 redist directory is accepted, never DLLs from System32.
    crt = args.crt_directory.resolve(strict=True)
    if crt.name != 'Microsoft.VC143.CRT' or crt.parent.name != 'x64': raise ValueError('Use the VS x64/Microsoft.VC143.CRT redistributable directory.')
    for required in ['vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll']:
        if not (crt / required).is_file(): raise ValueError('Incomplete C++ runtime: ' + required)
    for dll in crt.glob('*.dll'):
        x64(dll)
        copy(dll, 'bin/' + dll.name)
    for relative in ['marea.plm','marea.luau','marea-desktop.plm','marea-desktop.luau','LICENSE','common','lang','wardrobe','shaders','assets']:
        copy(ROOT / relative, 'app/' + relative)
    copy(ROOT / 'tools/reservas', 'app/tools/reservas')
    copy(ROOT / 'tools/deriva-preview.mjs', 'app/tools/deriva-preview.mjs')
    for name in ['desktop.ps1','run-desktop.ps1','installer-hooks.ps1']:
        copy(ROOT / 'windows' / name, 'windows/' + name)
    copy(ROOT / 'windows/DESKTOP.md', 'README.md')
    copy(ROOT / 'windows/INSTALLER.md', 'INSTALLER.md')
    notice = stage / 'bin/licenses/msvc/NOTICE.txt'
    notice.parent.mkdir(parents=True)
    notice.write_text('Microsoft Visual C++ runtime, copyright Microsoft Corporation.\n'
        'App-local files from Visual Studio x64/Microsoft.VC143.CRT.\n'
        'Redistribution is subject to the Visual Studio license and its Distributable Code list:\n'
        'https://visualstudio.microsoft.com/license-terms/\n'
        'https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution\n', encoding='utf-8', newline='\n')
    manifest = {'app_id': APP_ID, 'version': args.version, 'architecture': 'x86_64',
        'node_version': node_version, 'engine_source': args.engine_source,
        'marea_base': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT).decode().strip(),
        'files': {f.relative_to(stage).as_posix(): digest(f) for f in sorted(stage.rglob('*')) if f.is_file()}}
    (stage / 'package.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    host = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    run(host, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
        stage / 'windows/installer-hooks.ps1', '-Package', stage, '-Action', 'validate')
    run(args.iscc.resolve(), '/Qp', '/DPayload=' + str(stage), '/DAppVersion=' + args.version,
        '/O' + str(out), ROOT / 'windows/marea.iss')
    setup = out / f'Marea-{args.version}-windows-x64-setup.exe'
    (out / (setup.name + '.sha256')).write_text(digest(setup) + '  ' + setup.name + '\n', encoding='ascii')
    (out / 'build.json').write_text(json.dumps({'version': args.version, 'setup_sha256': digest(setup),
        'engine_sha256': digest(engine), 'worker_sha256': digest(worker), 'source': manifest,
        'signed': False, 'interactive_validation': False}, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Built {setup}; native preflight passed. GUI review and clean-machine validation remain separate.')

if __name__ == '__main__': main()
