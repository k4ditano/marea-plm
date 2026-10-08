"""Expand the upstream parts for the generated, standalone desktop profile."""
from pathlib import Path
import json
import os
import re
import textwrap


def scene_source(path: Path, stack=()):
    path = path.resolve()
    if path in stack:
        raise ValueError(f'Recursive scene include: {path}')
    source = path.read_text(encoding='utf-8')
    if stack:
        match = re.fullmatch(r'(?s).*?^part\s+\w+\s*\{\n(.*)\n\}\s*', source, re.M)
        if not match:
            raise ValueError(f'Expected a scene part: {path}')
        source = textwrap.dedent(match[1]) + '\n'

    # The compiler normally resolves resources beside the part declaring them.
    # A flattened profile lives beside marea.plm, so keep that resource identity
    # instead of exporting ../../shaders and looking outside the installed app.
    def resource(match):
        name = json.loads(match[2])
        if Path(name).is_absolute():
            return match[0]
        base = stack[0].parent if stack else path.parent
        relative = Path(os.path.relpath(path.parent / name, base)).as_posix()
        return match[1] + json.dumps(relative, ensure_ascii=False)

    source = re.sub(r'^(\s*(?:shader|figure)\s+[\w.]+\s*=\s*file\s+)("(?:[^"\\]|\\.)*")',
                    resource, source, flags=re.M)

    def include(match):
        child = path.parent / match[2]
        body = scene_source(child, (*stack, path))
        return textwrap.indent(body.rstrip('\n'), match[1]) + '\n'

    return re.sub(r'^([ \t]*)include "([^"\n]+)"[ \t]*$', include, source, flags=re.M)


def logic_source(root: Path):
    # These extracted functions used to live in the main chunk. Restore that
    # layout for the Windows transformations, while reading all implementation
    # from the current modules rather than a frozen copy of the old scene.
    functions = {'system': 'system_pages', 'deriva': 'deriva', 'software': 'software', 'chat': 'chat'}
    source = (root / 'marea.luau').read_text(encoding='utf-8')

    def module(match):
        name = match[2]
        content = (root / 'logic' / f'{name}.luau').read_text(encoding='utf-8')
        header, body = content.split('return function(shared)\n', 1)
        assert body.rstrip().endswith('\nend'), name
        body = body.rstrip()[:-4] + '\n'
        body = re.sub(r'^    local [\w, ]+ = shared\.[\w., ]+\n', '', body, flags=re.M)
        body = body.replace('shared.apps()', 'apps')
        assert 'shared.' not in body, f'New module dependencies need mapping: {name}'
        if name in functions:
            return header + f'local function {functions[name]}()\n' + body + f'end\n{functions[name]}()'
        body = re.sub(r'^    return \{ [^\n]+ \}\n', '', body, flags=re.M)
        return textwrap.dedent(body).rstrip('\n')

    source = re.sub(r'^(local \w+ = )?require\("logic/(\w+)"\)\((\{[^\n]+\})\)$', module, source, flags=re.M)
    source = re.sub(r'^local (paint_agents|hyprctl) = (agents_part|camera_part)\.\1\n', '', source, flags=re.M)
    assert not re.search(r'^(?!\s*--).*require\("logic/', source, re.M), 'An unexpanded logic module remains'
    return source
