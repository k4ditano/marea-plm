"""Prepare a draft GitHub prerelease from this run's tested Windows installer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def validate(args):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-preview\.[0-9]+', args.version):
        raise ValueError('Release preparation requires a preview version, such as 0.2.8-preview.1.')
    for repository in (args.repository, args.engine_repository, args.wm_repository):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Expected a GitHub owner/repository.')
    for commit in (args.marea_commit, args.engine_commit, args.wm_commit):
        if not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise ValueError('Use full commit hashes, not branches or tags.')
    if not re.fullmatch(r'[0-9]+', args.run_id):
        raise ValueError('Expected a GitHub Actions run ID.')
    metadata = args.directory / 'build.json'
    build = json.loads(metadata.read_text(encoding='utf-8'))
    report = json.loads(args.report.read_text(encoding='utf-8'))
    source = build['source']
    if (build['version'] != args.version or source['version'] != args.version
            or source['marea_base'] != args.marea_commit
            or source.get('marea_worktree_dirty') is not False
            or source['engine_source'] != args.engine_commit
            or source.get('wm_source') != args.wm_commit
            or source['architecture'] != 'x86_64'
            or source['app_id'] != 'A8D741A8-45D5-4DE8-A38E-27DA65D253F8'):
        raise ValueError('The package does not match the requested sources, version or identity.')
    setup = args.directory / f'Marea-{args.version}-windows-x64-setup.exe'
    checksum = setup.with_suffix('.exe.sha256')
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    if (build['setup_sha256'] != digest
            or checksum.read_text(encoding='ascii').strip() != f'{digest}  {setup.name}'):
        raise ValueError('The installer or its checksum has changed.')
    if report.get('passed') is not True or report.get('setup_sha256') != digest:
        raise ValueError('The installer has no matching successful lifecycle test.')
    if build.get('signed') is not False or build.get('interactive_validation') is not False:
        raise ValueError('Update the preview release notes before changing validation or signing claims.')
    notes = f"""Windows x64 preview. Download `{setup.name}` below and run it.

Includes pleamar with default Luau, the native Deriva worker, private Node.js,
the native AI host, locked Pi SDK, native window manager, C++ runtime and DXC. No developer tools or
separate Node install are needed. AI package checks use an empty account; an
authenticated model conversation and full desktop-agent validation remain separate.
Requires Windows 10 build 17763 or newer and a DX12 driver.
The window manager starts in free mode. Marea can opt into native tiling per
monitor; compositor effects and remote desktop parity remain unfinished.

Automated Windows installation, update, locked-file rejection and uninstall
tests passed for this exact installer. This does not establish graphical,
hardware or performance coverage. The installer is unsigned; the SHA-256 file
detects changed bytes and is not a publisher signature. This is not a stable release.

- [Build and test run](https://github.com/{args.repository}/actions/runs/{args.run_id})
- [Marea source](https://github.com/{args.repository}/commit/{args.marea_commit})
- [pleamar source](https://github.com/{args.engine_repository}/commit/{args.engine_commit})
- [pleamar-wm source](https://github.com/{args.wm_repository}/commit/{args.wm_commit})
- [Installation and limitations](https://github.com/{args.repository}/blob/{args.marea_commit}/windows/INSTALLER.md)

SHA-256: `{digest}`

Developed with Codex. Maintainers should review the notes and Windows tester
feedback before publishing this draft.
"""
    return [setup, checksum, metadata], notes


def create_draft(args):
    assets, notes = validate(args)
    tag = 'windows-v' + args.version
    # An existing tag could point at a different build. Never reuse or move it.
    refs = json.loads(subprocess.check_output([
        'gh', 'api', f'repos/{args.repository}/git/matching-refs/tags/{tag}',
    ], text=True, encoding='utf-8'))
    if any(ref['ref'] == 'refs/tags/' + tag for ref in refs):
        raise ValueError('This release tag already exists. Choose a new preview version.')
    with tempfile.TemporaryDirectory(prefix='marea-release-') as directory:
        path = Path(directory) / 'notes.md'
        path.write_text(notes, encoding='utf-8', newline='\n')
        result = subprocess.check_output([
            'gh', 'release', 'create', tag, *map(str, assets),
            '--repo', args.repository, '--target', args.marea_commit,
            '--title', f'Marea {args.version} (Windows x64 preview)',
            '--notes-file', str(path), '--draft', '--prerelease', '--latest=false',
        ], text=True, encoding='utf-8')
    print(result.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--marea-commit', required=True)
    parser.add_argument('--engine-repository', required=True)
    parser.add_argument('--engine-commit', required=True)
    parser.add_argument('--wm-repository', required=True)
    parser.add_argument('--wm-commit', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--run-id', required=True)
    create_draft(parser.parse_args())


if __name__ == '__main__':
    main()
