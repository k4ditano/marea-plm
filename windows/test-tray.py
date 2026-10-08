"""Check catalog overflow, stale rows and native action dispatch without Explorer."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks
parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('tray.luau').read_text(encoding='utf-8')
checks = r'''
local fact, text, model, handlers, notices, requests = {}, {}, {}, {}, {}, {}
local listener
local function on(name, callback) handlers[name] = callback end
local function notice(message) notices[#notices + 1] = message end
local sys = {
    watch = function(name, callback) assert(name == "tray"); listener = callback; return true end,
    call_async = function(name, args, callback) requests[#requests + 1] = { name, args[1], callback } end,
}
__MODULE__
local items = {}
for i = 1, 23 do items[i] = { key = "native:" .. i, id = "app" .. i, title = "App " .. i, icon = "" } end
listener(items)
assert(#model.icons == 4 and model.icons[4].more and model.icons[4].key == nil)
handlers.systray_activate(3)
assert(fact.page == "systray" and #model.options == 7)
for page = 1, 3 do handlers.systray_pick(#model.options - 1) end
assert(text["systray.title"] == "Aplicaciones · 4/4")
handlers.systray_pick(5)
assert(text["systray.title"] == "App 23")
handlers.systray_pick(2)
assert(#requests == 1 and requests[1][1] == "tray.context" and requests[1][2] == "native:23")
handlers.systray_activate(0)
assert(#requests == 1, "pending actions must not duplicate")
requests[1][3]("provider unavailable", -1)
assert(notices[1] == "provider unavailable")
handlers.systray_activate(-1); handlers.systray_activate(0.5); handlers.systray_activate(50)
assert(#requests == 1)
handlers.systray_activate(0)
assert(requests[2][1] == "tray.activate" and requests[2][2] == "native:1")
requests[2][3]("", 0)
handlers.systray_activate(3)
handlers.systray_pick(0)
assert(text["systray.title"] == "App 1")
table.remove(items, 1)
listener(items)
assert(text["systray.title"] == "Aplicaciones · 1/4", "removed selection must disappear")
listener({})
assert(#model.icons == 0 and #model.options == 0)
handlers.systray_activate(0); handlers.systray_pick(0)
assert(#requests == 2, "no stale action")
listener({ { key = "native:new", id = "Nuevo", title = "Español 日本語", icon = "" } })
handlers.systray_menu(0)
assert(requests[3][1] == "tray.context" and requests[3][2] == "native:new")
log("PASS: tray overflow, every catalog item reachable, native menus, pending and stale actions")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: tray overflow', 'tray')
