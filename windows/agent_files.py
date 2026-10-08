"""Inventory the pinned native AI bundle shared by both Windows installers."""
import argparse
import json
import os
from pathlib import Path
import stat
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NODE_VERSION = 'v22.23.3'
SOURCES = ('worker.mjs', 'tools.mjs', 'auth-interaction.mjs', 'state-image.mjs',
           'desktop-policy.mjs', 'package.json', 'package-lock.json')


def runtime_dependency(name):
    # Type declarations and compiler source maps are development metadata.
    # Keep executable TypeScript, arbitrary .map assets, prompts and licenses.
    return not name.endswith(('.d.ts', '.d.mts', '.d.cts', '.js.map', '.mjs.map',
                              '.cjs.map', '.ts.map', '.mts.map', '.cts.map'))


def x64(path):
    with path.open('rb') as stream:
        header = stream.read(64)
        if len(header) < 64 or header[:2] != b'MZ':
            raise ValueError(f'Not a PE image: {path}')
        stream.seek(struct.unpack_from('<I', header, 60)[0])
        if stream.read(6) != b'PE\0\0\x64\x86':
            raise ValueError(f'Not Windows x64: {path}')


def ordinary(path):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError(f'Agent package cannot contain links: {path}')
    return info


def collect(host, node_directory, root=ROOT):
    host, node_directory = Path(host).absolute(), Path(node_directory).absolute()
    node = node_directory / 'node.exe'
    for executable in (host, node):
        ordinary(executable)
        x64(executable)
    version = subprocess.check_output([str(node), '--version'], timeout=15,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).decode().strip()
    if version != NODE_VERSION:
        raise ValueError(f'Expected Node {NODE_VERSION}, found {version}')
    code = root / 'agent'
    ordinary(code)
    package = json.loads((code / 'package.json').read_text(encoding='utf-8'))
    lock = json.loads((code / 'package-lock.json').read_text(encoding='utf-8'))
    installed = json.loads((code / 'node_modules/.package-lock.json').read_text(encoding='utf-8'))
    if package['dependencies'] != lock['packages']['']['dependencies']:
        raise ValueError('Agent package and dependency lock disagree; run npm ci.')
    expected = lock['packages']
    actual = installed['packages']
    for relative, metadata in actual.items():
        if relative not in expected or any(metadata.get(k) != expected[relative].get(k)
                for k in ('version', 'resolved', 'integrity')):
            raise ValueError(f'Unpinned installed dependency: {relative}; run npm ci.')
        dependency = code / relative / 'package.json'
        if json.loads(dependency.read_text(encoding='utf-8'))['version'] != metadata['version']:
            raise ValueError(f'Installed dependency version mismatch: {relative}')
    for relative, metadata in expected.items():
        if relative and not metadata.get('optional') and relative not in actual:
            raise ValueError(f'Missing required dependency: {relative}; run npm ci.')
    files = {'bin/marea-agent.exe': host, 'bin/node.exe': node,
             'bin/licenses/node/LICENSE': node_directory / 'LICENSE'}
    for relative in SOURCES:
        files['app/agent/' + relative] = code / relative
    # Keep dependency runtime files and license/notice texts together. npm's
    # command shims are unnecessary: the worker imports modules directly.
    modules = code / 'node_modules'
    for directory, children, names in os.walk(modules, followlinks=False):
        directory = Path(directory)
        ordinary(directory)
        children[:] = sorted(name for name in children if name != '.bin')
        for name in children:
            ordinary(directory / name)
            relative = (directory / name).relative_to(code).as_posix()
            package_folder = (directory.name == 'node_modules' and not name.startswith('@'))
            scoped_folder = directory.parent.name == 'node_modules' and directory.name.startswith('@')
            if (package_folder or scoped_folder) and relative not in actual:
                raise ValueError(f'Unrecorded dependency directory: {relative}; run npm ci.')
        for name in sorted(names):
            source = directory / name
            ordinary(source)
            if directory == modules and name != '.package-lock.json':
                raise ValueError(f'Unrecorded dependency-root file: {name}; run npm ci.')
            if runtime_dependency(name):
                files['app/agent/' + source.relative_to(code).as_posix()] = source
    for source in files.values():
        if not stat.S_ISREG(ordinary(source).st_mode):
            raise ValueError(f'Missing regular agent input: {source}')
    return {'node_version': version,
            'sdk_version': package['dependencies']['@earendil-works/pi-coding-agent'],
            'files': {relative: str(path) for relative, path in sorted(files.items())}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, required=True)
    parser.add_argument('--node-directory', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.host, args.node_directory), ensure_ascii=True))
