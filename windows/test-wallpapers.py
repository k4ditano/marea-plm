"""Exercise wallpaper confirmation and queue failures without changing the desktop."""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description=__doc__)
from logic_test import runner_arguments, run_checks
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('wallpapers.luau').read_text(encoding='utf-8')
checks = r'''
local fact, model, handlers, requests, events, notices = {
    ["tide.on"] = true, ["screens.count"] = 1,
    ["screen.0.width"] = 820, ["screen.0.height"] = 680,
    ["windows_tide_width.0"] = 2048, ["windows_tide_height.0"] = 1152,
}, {}, {}, {}, {}, {}
local text = {["screen.0.name"] = "DISPLAY1", ["screen.1.name"] = "DISPLAY2"}
local WALLPAPER, saves, reject = "", 0, false
local function on(name, callback) handlers[name] = callback end
local function emit(name) events[#events + 1] = name end
local function notice(message) notices[#notices + 1] = message end
local function save_settings() saves += 1 end
local function queue(name, args, callback)
    if reject then error("service queue full") end
    requests[#requests + 1] = { name = name, args = args, callback = callback }
end
local native_sys = { ask_async = queue, call_async = queue }
local function complete(name, value, error)
    local request = table.remove(requests, 1)
    assert(request and request.name == name, "unexpected request: " .. name)
    request.callback(value, error)
end
__MODULE__
assert(fact["tide.on"] == false, "reload left the abandoned transition covering the desktop")
handlers.tide_done()
assert(#requests == 1, "an abandoned transition committed a wallpaper after reload")
complete("wallpaper.state", { current = "C:/original.png" })
assert(model.wallnow[1].ready and model.wallnow[1].thumb == "C:/original.png")
handlers.walls_open()
complete("wallpaper.list", { current = "C:/original.png", items = {
    { name = "Original", path = "C:/original.png" }, { name = "New", path = "C:/new.png" },
} })
handlers.wall_pick(0)
assert(#requests == 0, "selecting the current wallpaper should not change Windows")
reject = true
handlers.wall_pick(1)
assert(#notices > 0 and saves == 0, "enqueue failure was hidden")
reject = false
handlers.wall_pick(1)
complete("wallpaper.preview", nil, "invalid image")
assert(notices[#notices] == "invalid image" and saves == 0)
local function choose()
    handlers.wall_pick(1)
    assert(requests[1].args[2] == 2048 and requests[1].args[3] == 1152, "the panel's size is not the wallpaper crop")
    complete("wallpaper.preview", "C:/preview.jpg")
    assert(events[#events] == "tide_start" and #requests == 0)
    handlers.tide_done()
end
choose()
complete("wallpaper.set", "device error", -1)
assert(events[#events] == "tide_away" and saves == 0)
choose()
complete("wallpaper.set", "", 0)
complete("wallpaper.state", { current = "C:/original.png" })
assert(saves == 0 and WALLPAPER == "C:/original.png", "unconfirmed wallpaper was persisted")
choose()
complete("wallpaper.set", "", 0)
complete("wallpaper.state", { current = "c:\\new.png" })
assert(saves == 1 and model.walls[2].current and events[#events] == "tide_away")
assert(#requests == 0)
-- Different resolutions/aspect ratios get separate pictures and start together.
fact["screens.count"] = 2
fact["windows_tide_width.1"], fact["windows_tide_height.1"] = 864, 1536
fact["hosts.1"] = true
local before = #events
handlers.wall_pick(0)
complete("wallpaper.preview", "C:/landscape.jpg")
assert(#events == before, "started before the second monitor was prepared")
assert(requests[1].args[2] == 864 and requests[1].args[3] == 1536)
complete("wallpaper.preview", "C:/portrait.jpg")
assert(model.tidepics[1].pic == "C:/landscape.jpg" and model.tidepics[2].pic == "C:/portrait.jpg")
assert(fact["tide.home"] == 1 and events[#events] == "tide_start")
handlers.tide_done(); complete("wallpaper.set", "failure", -1)
-- A failed second preview or a changed monitor must not start or commit.
before = #events
handlers.wall_pick(0)
complete("wallpaper.preview", "C:/landscape.jpg")
complete("wallpaper.preview", nil, "second preview failed")
assert(#events == before and #requests == 0)
handlers.wall_pick(0)
complete("wallpaper.preview", "C:/landscape.jpg")
fact["windows_tide_width.1"] = 1536
complete("wallpaper.preview", "C:/portrait.jpg")
assert(#events == before and #requests == 0 and saves == 1)
-- The third upstream copy is also a native display. Prepare every crop before
-- showing the transition, and anchor it to the display which hosts Marea.
fact["screens.count"] = 3
fact["hosts.1"] = false; fact["hosts.2"] = true
text["screen.2.name"] = "DISPLAY3 ñ"
fact["windows_tide_width.2"], fact["windows_tide_height.2"] = 1600, 900
before = #events
handlers.wall_pick(0)
complete("wallpaper.preview", "C:/landscape.jpg")
complete("wallpaper.preview", "C:/portrait.jpg")
assert(#events == before and #requests == 1, "third monitor was omitted from the wallpaper transition")
assert(requests[1].args[2] == 1600 and requests[1].args[3] == 900)
complete("wallpaper.preview", "C:/third.jpg")
assert(#model.tidepics == 3 and model.tidepics[3].pic == "C:/third.jpg")
assert(fact["tide.home"] == 2 and events[#events] == "tide_start")
handlers.tide_done(); complete("wallpaper.set", "failure", -1)
-- Reject a third display removed or renamed while its image was prepared.
for _, change in ipairs({"remove", "rename"}) do
    fact["screens.count"] = 3; text["screen.2.name"] = "DISPLAY3 ñ"
    before = #events
    handlers.wall_pick(0)
    complete("wallpaper.preview", "C:/landscape.jpg")
    complete("wallpaper.preview", "C:/portrait.jpg")
    if change == "remove" then fact["screens.count"] = 2 else text["screen.2.name"] = "Replacement display" end
    complete("wallpaper.preview", "C:/third.jpg")
    assert(#events == before and #requests == 0 and saves == 1)
end
fact["windows_tide_width.0"] = 0
handlers.wall_pick(0)
assert(#requests == 0 and #events == before, "unconfigured geometry used an arbitrary fallback")
log("PASS: wallpaper preview, queue failure, retries, native failure and confirmed persistence")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: wallpaper preview', 'wallpapers')
