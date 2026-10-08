"""Generated dynamic menu follows saved language and shelf state without fact echoes."""
from pathlib import Path
import argparse, json, re
from logic_test import runner_arguments, run_checks
parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
logic = (root / 'marea-desktop.luau').read_text(encoding='utf-8')
scene = (root / 'marea-desktop.plm').read_text(encoding='utf-8')
assert 'windows_shelf_toggle' not in scene and 'windows_shelf_hint' not in scene
translations = {}
for path in (root / 'lang').glob('es*.plm'):
    for a, b in re.findall(r'("(?:[^"\\]|\\.)*")\s*=\s*("(?:[^"\\]|\\.)*")', path.read_text(encoding='utf-8')):
        translations[json.loads(a)] = json.loads(b)
translations.update(json.loads((root / 'windows/translations.json').read_text(encoding='utf-8')))
entries = 'local plugin_entries = {' + logic.split('local plugin_entries = {', 1)[1].split('\n}', 1)[0] + '\n}'
menu = 'local function set_menu()' + logic.split('local function set_menu()', 1)[1].split('-- ── the swell,', 1)[0]
language = 'local LOCALES = ' + logic.split('local LOCALES = ', 1)[1].split('on("fact:language", function() speak(); save_settings() end)', 1)[0] + 'on("fact:language", function() speak(); save_settings() end)'
checks = r'''
local fact, model, handlers, events = {}, {}, {}, {}
local hooks = {language = {}}
local settings = {language="spanish"}
local function on(n, fn) handlers[n] = fn end
local function emit(n) events[#events+1] = n end
local function render() end
local function search() end
local function save_settings() end
local function system_locale() return "en" end
local translations = __TRANSLATIONS__
local function tr(s) return fact.locale == "es" and translations[s] or s end
__ENTRIES__
__MENU__
assert(model.entries[1].title == "Tuck applications away")
__LANGUAGE__
assert(fact.locale == "es" and model.entries[1].title == "Recoger aplicaciones")
for _, e in ipairs(model.entries) do
    assert(e.group_name ~= "Desktop" and e.group_name ~= "Drift" and e.group_name ~= "Swell")
    assert(e.title ~= "Her library" and e.title ~= "Keep what is copied" and e.title ~= "History" and e.title ~= "Wallpapers")
end
handlers.menu_entry(0); assert(events[#events] == "windows_toggle_shelf")
fact.windows_shelf_folded = true
handlers["fact:windows_shelf_folded"]()
assert(model.entries[1].title == "Mostrar aplicaciones")
fact.language = "english"; handlers["fact:language"]()
assert(model.entries[1].title == "Show applications" and model.entries[1].group_name == "Desktop")
fact.language = "spanish"; handlers["fact:language"]()
assert(model.entries[1].title == "Mostrar aplicaciones")
log("PASS: saved language, dynamic context menu translations, shelf action/state and English/Spanish switching")
'''
dictionary = '{' + ',\n'.join('[' + json.dumps(k, ensure_ascii=False) + ']=' + json.dumps(v, ensure_ascii=False) for k, v in translations.items()) + '}'
for name, value in [('TRANSLATIONS', dictionary), ('ENTRIES', entries), ('MENU', menu), ('LANGUAGE', language)]:
    checks = checks.replace('__' + name + '__', value)
run_checks(args, checks, 'PASS: saved language', 'menu-language')
