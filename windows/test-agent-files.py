"""Distribution inventory keeps SDK runtime assets and rejects redirected files."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import agent_files


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='marea inventory ñ ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.code = self.root / 'agent'
        self.dependency = self.code / 'node_modules/sdk-fixture'
        self.dependency.mkdir(parents=True)
        self.node = self.root / 'node'
        self.node.mkdir()
        # A minimal PE header permits inventory validation without running code.
        pe = b'MZ' + bytes(58) + (64).to_bytes(4, 'little') + b'PE\0\0\x64\x86'
        self.host = self.root / 'host.exe'
        self.host.write_bytes(pe)
        (self.node / 'node.exe').write_bytes(pe)
        (self.node / 'LICENSE').write_text('Node fixture license')
        dependencies = {'@earendil-works/pi-coding-agent': 'fixture'}
        metadata = {'version': '1', 'resolved': 'fixture', 'integrity': 'fixture'}
        for name in agent_files.SOURCES:
            (self.code / name).write_text('// owned fixture')
        (self.code / 'package.json').write_text(json.dumps({'dependencies': dependencies}))
        (self.code / 'package-lock.json').write_text(json.dumps({'packages': {
            '': {'dependencies': dependencies}, 'node_modules/sdk-fixture': metadata}}))
        (self.code / 'node_modules/.package-lock.json').write_text(json.dumps({
            'packages': {'node_modules/sdk-fixture': metadata}}))
        (self.dependency / 'package.json').write_text(json.dumps({'version': '1', 'main': 'api.js', 'types': 'api.d.ts'}))

    def inventory(self):
        with patch.object(agent_files.subprocess, 'check_output', return_value=b'v22.23.3\n'):
            return agent_files.collect(self.host, self.node, self.root)['files']

    def test_distribution_retains_runtime_assets_and_licenses(self):
        runtime = ['api.js', 'api.mjs', 'api.cjs', 'extension.ts', 'world.map',
                   'prompt.md', 'README.md', 'LICENSE', 'NOTICE', 'data.json', 'native.node']
        metadata = ['api.d.ts', 'api.d.mts', 'api.d.cts', 'api.js.map',
                    'api.mjs.map', 'api.cjs.map', 'api.d.ts.map']
        for name in runtime + metadata:
            (self.dependency / name).write_text('owned fixture')
        files = self.inventory()
        prefix = 'app/agent/node_modules/sdk-fixture/'
        for name in runtime:
            self.assertIn(prefix + name, files)
        for name in metadata:
            self.assertNotIn(prefix + name, files)
        self.assertIn(prefix + 'package.json', files)
        self.assertIn('bin/licenses/node/LICENSE', files)

    def test_excluded_metadata_still_cannot_redirect_outside_the_package(self):
        outside = self.root / 'unrelated.txt'
        outside.write_text('unrelated data')
        link = self.dependency / 'api.d.ts'
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f'This host cannot create the owned symlink fixture: {error}')
        with self.assertRaisesRegex(ValueError, 'cannot contain links'):
            self.inventory()


if __name__ == '__main__':
    unittest.main()
