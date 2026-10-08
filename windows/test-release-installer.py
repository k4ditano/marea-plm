"""Exercise release rejection paths without uploading or publishing anything."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('release_installer', Path(__file__).with_name('release-installer.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='marea-release-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.args = argparse.Namespace(directory=self.root, report=self.root / 'report.json',
            repository='owner/marea', marea_commit='a' * 40,
            engine_repository='owner/pleamar', engine_commit='b' * 40,
            wm_repository='owner/pleamar-wm', wm_commit='d' * 40,
            version='0.2.8-preview.1', run_id='123')
        self.setup = self.root / 'Marea-0.2.8-preview.1-windows-x64-setup.exe'
        self.setup.write_bytes(b'installer fixture')
        digest = hashlib.sha256(self.setup.read_bytes()).hexdigest()
        self.checksum = self.setup.with_suffix('.exe.sha256')
        self.checksum.write_text(f'{digest}  {self.setup.name}\n', encoding='ascii')
        self.build = dict(version=self.args.version, setup_sha256=digest,
            signed=False, interactive_validation=False,
            source=dict(version=self.args.version, architecture='x86_64',
                marea_base=self.args.marea_commit, engine_source=self.args.engine_commit,
                wm_source=self.args.wm_commit,
                marea_worktree_dirty=False,
                app_id='A8D741A8-45D5-4DE8-A38E-27DA65D253F8'))
        self.report = dict(passed=True, setup_sha256=digest)
        self.save()

    def save(self):
        (self.root / 'build.json').write_text(json.dumps(self.build), encoding='utf-8')
        self.args.report.write_text(json.dumps(self.report), encoding='utf-8')

    def rejected(self):
        with patch.object(release.subprocess, 'check_output') as remote:
            with self.assertRaises(ValueError):
                release.create_draft(self.args)
            remote.assert_not_called()

    def test_changed_installer(self):
        self.setup.write_bytes(b'changed after tests')
        self.rejected()

    def test_changed_checksum(self):
        self.checksum.write_text('wrong', encoding='ascii')
        self.rejected()

    def test_failed_lifecycle(self):
        self.report['passed'] = False
        self.save()
        self.rejected()

    def test_lifecycle_from_another_installer(self):
        self.report['setup_sha256'] = 'c' * 64
        self.save()
        self.rejected()

    def test_package_from_another_commit(self):
        self.build['source']['marea_base'] = 'c' * 40
        self.save()
        self.rejected()

    def test_engine_from_another_commit(self):
        self.build['source']['engine_source'] = 'c' * 40
        self.save()
        self.rejected()

    def test_uncommitted_package_sources(self):
        self.build['source']['marea_worktree_dirty'] = True
        self.save()
        self.rejected()

    def test_window_manager_from_another_commit(self):
        self.build['source']['wm_source'] = 'c' * 40
        self.save()
        self.rejected()

    def test_missing_window_manager_source(self):
        del self.build['source']['wm_source']
        self.save()
        self.rejected()

    def test_missing_source_cleanliness(self):
        del self.build['source']['marea_worktree_dirty']
        self.save()
        self.rejected()

    def test_no_stable_release(self):
        self.args.version = '0.2.8'
        self.rejected()

    def test_no_branch_instead_of_commit(self):
        self.args.engine_commit = 'main'
        self.rejected()

    def test_existing_tag_cannot_be_reused(self):
        refs = [{'ref': 'refs/tags/windows-v' + self.args.version}]
        with patch.object(release.subprocess, 'check_output', return_value=json.dumps(refs)) as remote:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                release.create_draft(self.args)
            self.assertEqual(remote.call_count, 1)

    def test_release_is_draft_and_only_expected_assets_are_uploaded(self):
        def command(arguments, **kwargs):
            if arguments[1] == 'api':
                return '[]'
            self.assertIn('--draft', arguments)
            self.assertIn('--prerelease', arguments)
            self.assertIn('--latest=false', arguments)
            self.assertEqual(arguments[4:7], [str(self.setup), str(self.checksum), str(self.root / 'build.json')])
            self.assertEqual(arguments[arguments.index('--target') + 1], self.args.marea_commit)
            notes = Path(arguments[arguments.index('--notes-file') + 1]).read_text(encoding='utf-8')
            self.assertIn('installer is unsigned', notes)
            self.assertIn('does not establish graphical', notes)
            self.assertIn('/actions/runs/123', notes)
            self.assertNotIn(str(self.root), notes)
            return 'https://github.com/owner/marea/releases/draft'
        with patch.object(release.subprocess, 'check_output', side_effect=command):
            release.create_draft(self.args)


if __name__ == '__main__':
    unittest.main()
