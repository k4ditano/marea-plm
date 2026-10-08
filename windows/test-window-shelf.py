"""Exercise native catalog updates and restore sequencing without real windows."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('window-shelf.luau').read_text(encoding='utf-8')
checks = r'''
local hooks, model, handlers, requests, notices = {}, {}, {}, {}, {}
local reject = false
local function on(name, callback) handlers[name] = callback end
local function notice(message) notices[#notices + 1] = message end
local native_sys = { call_async = function(name, args, callback)
    if reject then error("queue full") end
    assert(name == "window.restore" and #requests == 0, "restore must be serialized")
    requests[1] = { id = args[1], callback = callback }
end }
local function complete(id, error)
    local request = table.remove(requests, 1)
    assert(request and request.id == id, "wrong restored window")
    request.callback(error or "", error and -1 or 0)
end
local function window(id, title, icon)
    return { id = id, minimized = true, title = title or ("Window " .. id), icon = icon or "" }
end
__MODULE__
set_stones({ window(10, "Álbum"), window(20, "Editor", "windows-file:C:/Apps/Editor.exe") })
assert(model.stones[1].letter == "Á" and model.stones[2].letter == "")
local seq = model.stones[1].seq
set_stones({ window(20), window(10, "Renamed", "windows-file:C:/Apps/Player.exe") })
assert(model.stones[1].title == "Renamed" and model.stones[1].seq == seq)
assert(model.stones[1].icon:find("Player"))
handlers.restore_stone(0)
handlers.restore_stone(0)
assert(#requests == 1)
complete(10)
handlers.restore_stone(-1); handlers.restore_stone(6); handlers.restore_stone(0.5)
assert(#requests == 0)
set_stones({ window(20), window(30, "新しい") })
assert(model.stones[1].title == "新しい" and model.stones[1].letter == "新")
assert(model.stones[2].title == "Window 20" and model.stones[1].seq > seq)
local many = {}
for id = 1, 12 do many[id] = window(id) end
set_stones(many)
assert(#model.stones == 6)
hooks.restore_all(); hooks.restore_all()
complete(1, "application hung")
table.remove(many, 3)
set_stones(many)
complete(2)
for id = 4, 12 do complete(id) end
assert(#requests == 0 and notices[#notices] == "application hung")
reject = true
hooks.restore_all()
assert(#requests == 0 and notices[#notices]:find("queue full"))
reject = false
hooks.restore_all()
set_stones({})
complete(1)
assert(#requests == 0 and not model.stones[1].present)
log("PASS: stable window slots, live title/icon updates, Unicode, bounded restore-all and failures")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: stable window slots', 'window-shelf')
