"""The desktop generator reads current parts and module implementations."""
from pathlib import Path
import runpy
import tempfile
import unittest

API = runpy.run_path(str(Path(__file__).with_name('profile-source.py')))


class SourceTests(unittest.TestCase):
    def test_flattened_resources_still_resolve_to_the_part_assets(self):
        with tempfile.TemporaryDirectory(prefix='marea resources ñ ') as tmp:
            root = Path(tmp)
            (root / 'scene' / 'nested').mkdir(parents=True)
            (root / 'art ñ').mkdir()
            asset = root / 'art ñ' / 'hat.svg'
            asset.write_text('<svg/>', encoding='utf-8')
            (root / 'marea.plm').write_text('scene Marea {\n    include "scene/card.plm"\n}\n')
            (root / 'scene/card.plm').write_text('part Card {\n    include "nested/art.plm"\n}\n')
            (root / 'scene/nested/art.plm').write_text('part Art {\n    figure hat = file "../../art ñ/hat.svg"\n    shader tide = file "../../shaders/tide.wgsl"\n}\n', encoding='utf-8')
            result = API['scene_source'](root / 'marea.plm')
            self.assertIn('figure hat = file "art ñ/hat.svg"', result)
            self.assertIn('shader tide = file "shaders/tide.wgsl"', result)
            self.assertEqual((root / 'art ñ/hat.svg').read_text(), asset.read_text())

    def test_nested_parts_are_relative_and_keep_scope_and_unicode(self):
        with tempfile.TemporaryDirectory(prefix='marea parts ñ ') as tmp:
            root = Path(tmp)
            parts = root / 'some parts'
            parts.mkdir()
            (root / 'marea.plm').write_text('scene Marea {\n    include "some parts/card.plm"\n}\n', encoding='utf-8')
            (parts / 'card.plm').write_text('part Card {\n    group {\n        include "label.plm"\n    }\n}\n', encoding='utf-8')
            (parts / 'label.plm').write_text('part Label {\n    text "Música" { at: 0, 0 }\n}\n', encoding='utf-8')
            result = API['scene_source'](root / 'marea.plm')
            self.assertIn('    group {\n        text "Música"', result)
            self.assertNotIn('part Label', result)
            (parts / 'label.plm').write_text('part Label {\n    text "New value" { at: 0, 0 }\n}\n', encoding='utf-8')
            self.assertIn('New value', API['scene_source'](root / 'marea.plm'))

    def test_recursive_and_nonpart_inputs_fail_instead_of_producing_a_partial_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'marea.plm').write_text('scene Marea {\n    include "loop.plm"\n}\n')
            (root / 'loop.plm').write_text('part Loop {\n    include "loop.plm"\n}\n')
            with self.assertRaisesRegex(ValueError, 'Recursive scene include'):
                API['scene_source'](root / 'marea.plm')
            (root / 'loop.plm').write_text('library Example { }\n')
            with self.assertRaisesRegex(ValueError, 'Expected a scene part'):
                API['scene_source'](root / 'marea.plm')

    def test_new_module_dependencies_require_an_explicit_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'logic').mkdir()
            (root / 'marea.luau').write_text('require("logic/chat")({ hooks = hooks })\n')
            module = root / 'logic/chat.luau'
            module.write_text('return function(shared)\n    local hooks = shared.hooks\n    local a = shared.apps()\n    hooks.chat = function() return a end\nend\n')
            source = API['logic_source'](root)
            self.assertIn('local function chat()', source)
            self.assertIn('local a = apps', source)
            module.write_text('return function(shared)\n    shared.new_dependency()\nend\n')
            with self.assertRaisesRegex(AssertionError, 'New module dependencies'):
                API['logic_source'](root)


if __name__ == '__main__':
    unittest.main()
