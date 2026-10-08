"""Auto-hide defaults, saved choice and failed writes through the actual module."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('auto-hide.luau').read_text(encoding='utf-8')
checks = r'''
local fact, handlers, notices = {}, {}, {}
local function on(name, callback) handlers[name] = callback end
local function tr(value) return value end
local function notice(message) notices[#notices + 1] = message end
local install = (function() __MODULE__ end)()
local saved, reject, writes = nil, false, 0
local storage = {call = function(name, path, value)
    assert(name == "files.write" and path == "settings.json")
    if reject then error("read-only directory") end
    saved = table.clone(value); writes += 1
end}
local settings = {home="Monitor ñ", language="spanish", follow=true}
install(settings, storage, notice)
assert(fact.hidden == true and writes == 0, "default should match upstream without rewriting settings")
handlers.windows_toggle_autohide()
assert(fact.hidden == false and settings.auto_hide == false and saved.auto_hide == false)
assert(saved.home == "Monitor ñ" and saved.language == "spanish" and saved.follow == true)
install(table.clone(saved), storage, notice)
assert(fact.hidden == false, "saved opt-out was lost on restart")
reject = true
handlers.windows_toggle_autohide()
assert(fact.hidden == false and saved.auto_hide == false and writes == 1)
assert(#notices == 1 and notices[1] == "Could not save auto-hide preference")
reject = false
handlers.windows_toggle_autohide()
assert(fact.hidden == true and saved.auto_hide == true and writes == 2)
install(table.clone(saved), storage, notice)
assert(fact.hidden == true, "saved opt-in was lost on restart")
log("PASS: auto-hide default, persistent choices, unrelated settings and failed writes")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: auto-hide default', 'auto-hide')
