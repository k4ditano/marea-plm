"""Route brightness and the WM overview to Marea's third native monitor."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
adapter = (root / 'windows/desktop-adapter.luau').read_text(encoding='utf-8')
brightness = adapter[adapter.index('local brightness_monitor,'):adapter.index('on("windows_display_info"')]
generated = (root / 'marea-desktop.luau').read_text(encoding='utf-8')
monitor = generated.split('end)()(native_run, hooks, plugin_entries, set_menu, function()', 1)[1].split('end, notice, native_spawn)', 1)[0]
decision = generated[generated.index('local function decide()'):generated.index('--  Her wardrobe\'s pieces')]
placement = generated[generated.index('local function place()'):generated.index('local stone_slots')]
checks = r'''
local fact, text, handlers, calls, notices = {}, {}, {}, {}, {}
local monitors = {"DISPLAY1", "DISPLAY2", "Third display ñ 海"}
local function on(name, callback) handlers[name] = callback end
local function notice(message) notices[#notices + 1] = message end
local native_sys = {call_async = function(name, args, done)
    assert(name == "brightness.monitor")
    calls[#calls + 1] = args[1]
    done("", 0)
end}
fact["hosts.2"] = true
__BRIGHTNESS__
assert(#calls == 0, "an unnamed display sent a native brightness command")
for k = 0, 2 do
    assert(handlers["text:screen."..k..".name"] and handlers["fact:hosts."..k], "display subscriptions are missing")
    text["screen."..k..".name"] = monitors[k + 1]
    handlers["text:screen."..k..".name"]()
end
assert(#calls == 1 and calls[1] == monitors[3], "third monitor did not select its own brightness")
local function current_monitor() __MONITOR__ end
assert(current_monitor() == monitors[3], "overview was routed away from the third monitor")
text["screen.2.name"] = "Replacement monitor 海"
handlers["text:screen.2.name"]()
assert(calls[2] == "Replacement monitor 海")
fact["hosts.2"] = false; fact["hosts.0"] = true
handlers["fact:hosts.2"](); handlers["fact:hosts.0"]()
assert(#calls == 3 and calls[3] == monitors[1] and current_monitor() == monitors[1])
fact["hosts.0"] = false
assert(current_monitor() == nil)
local settings = {home = monitors[3], follow = false, room = false}
local focused, pointed = "", nil
local function tell_island() end
fact["screens.count"] = 3
text["screen.2.name"] = monitors[3]
__DECISION__
__PLACEMENT__
place()
assert(fact.home == 2 and fact["hosts.2"])
local before = #calls
fact["screens.count"] = 2
assert(handlers["fact:screens.count"], "unplugging the home display cannot relocate Marea")
handlers["fact:screens.count"](2)
assert(fact.home == 0 and fact["hosts.0"] and not fact["hosts.2"], "Marea stayed on the unplugged monitor")
assert(settings.home == "Third display ñ 海", "temporary unplug lost the saved home")
assert(#calls > before and calls[#calls] == "DISPLAY1", "Lua home changes did not select native brightness")
fact["screens.count"] = 3; handlers["fact:screens.count"](3)
assert(fact.home == 2 and fact["hosts.2"] and calls[#calls] == settings.home)
fact.following = true; focused = "DISPLAY2"; decide()
assert(fact["hosts.1"] and not fact["hosts.2"] and calls[#calls] == "DISPLAY2")
focused = "Not a displayed Marea copy"; decide()
assert(fact["hosts.2"], "an unknown focused display hid every copy")
fact["screens.count"] = 0; handlers["fact:screens.count"](0)
assert(not fact["hosts.0"] and not fact["hosts.1"] and not fact["hosts.2"])
fact["screens.count"] = 1; handlers["fact:screens.count"](1)
assert(fact.home == 0 and fact["hosts.0"])
before = #calls
for _ = 1, 20 do decide() end
assert(#calls == before, "unchanged focus repeatedly dispatched brightness selection")
local pending = {}
native_sys.call_async = function(name, args, done)
    calls[#calls + 1] = args[1]; pending[#pending + 1] = done
end
fact["screens.count"] = 3; handlers["fact:screens.count"](3)
fact.following = false; fact.home = 1; decide()
fact.home = 2; decide()
assert(#pending == 3)
before = #calls
pending[1]("late failure for the same monitor", 1)
pending[2]("late failure for the previous monitor", 1)
decide()
assert(#calls == before and #notices == 0, "stale selection failure replaced the newer choice")
pending[3]("current selection failed", 1)
decide()
assert(#calls == before + 1 and #notices == 1)
pending[4]("", 0)
log("PASS: all three native monitor routes, late names and changing home")
'''.replace('__BRIGHTNESS__', brightness).replace('__MONITOR__', monitor).replace('__DECISION__', decision).replace('__PLACEMENT__', placement)
run_checks(args, checks, 'PASS: all three native monitor routes', 'display-routing')
