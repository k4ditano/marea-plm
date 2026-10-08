"""Prepare the pinned Microsoft WinGet client for Windows PowerShell x64."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

VERSION = '1.29.380'
SHA256 = '3469e5747eb6b100e51fed3f2057386b5ba60bc8955a6669b5c2eb562e316619'
URL = f'https://www.powershellgallery.com/api/v2/package/Microsoft.WinGet.Client/{VERSION}'
ROOT = Path(__file__).resolve().parents[1]


def prepare(output, archive=None):
    output.mkdir(parents=True, exist_ok=True)
    archive = archive or output.parent / f'winget-{VERSION}.zip'
    if not archive.exists():
        with urllib.request.urlopen(URL, timeout=60) as response:
            archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError('WinGet client archive checksum mismatch')
    files = {}
    with zipfile.ZipFile(archive) as package:
        for name in package.namelist():
            # Retain signed originals and notices. No global module installation,
            # PowerShell 7, ARM or x86 binaries are needed by this x64 profile.
            if name in ('Microsoft.WinGet.Client.psd1', 'Format.ps1xml', 'NOTICE.txt') or (
                name.startswith('net48/') and '/arm64/' not in name and '/x86/' not in name):
                target = output / name
                target.parent.mkdir(parents=True, exist_ok=True)
                content = package.read(name)
                target.write_bytes(content)
                files[name] = hashlib.sha256(content).hexdigest()
    license_text = (ROOT / 'windows/licenses/winget-LICENSE.txt').read_bytes()
    (output / 'LICENSE.txt').write_bytes(license_text)
    files['LICENSE.txt'] = hashlib.sha256(license_text).hexdigest()
    (output / 'bundle.json').write_text(json.dumps(dict(version=VERSION, archive_sha256=SHA256,
        source=URL, files=files), indent=2) + '\n', encoding='utf-8')
    print(f'Prepared WinGet {VERSION}: {len(files)} verified files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/winget')
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    prepare(args.output, args.archive)
