"""Exercise capture state/errors in real Luau without reading the user's screen."""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description=__doc__)
from logic_test import runner_arguments, run_checks
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('screenshots.luau').read_text(encoding='utf-8')
checks = r'''
local fact, text, handlers, requests, events, notices = {}, {}, {}, {}, {}, {}
local reject = false
local function on(name, callback) handlers[name] = callback end
local function emit(name) events[#events + 1] = name end
local function notice(message) notices[#notices + 1] = message end
local function after(_, callback) callback() end
local native_sys = { ask_async = function(name, args, callback)
    if reject then error("queue full") end
    requests[#requests + 1] = { name = name, args = args, callback = callback }
end }
local function complete(name, value, error)
    local request = table.remove(requests, 1)
    assert(request and request.name == name, "unexpected request: " .. name)
    request.callback(value, error)
end
__MODULE__
local function begin(scope)
    fact.purpose = "shot"; fact.scope = scope; fact.windows_capture_busy = true
    handlers.gone()
end
begin("display")
handlers.gone()
assert(#requests == 1, "duplicate gone captured twice")
complete("screenshot.freeze", nil, "desktop unavailable")
assert(not fact.windows_capture_busy and events[#events] == "shot_cancelled")
begin("region")
complete("screenshot.freeze", 7)
assert(events[#events] == "frozen" and requests[1].args[1] == 7)
complete("screenshot.finish", { cancelled = true })
assert(not fact.windows_capture_busy and events[#events] == "shot_cancelled" and text.windows_capture_path == nil)
begin("active_window")
complete("screenshot.freeze", 8)
complete("screenshot.finish", nil, "disk full")
assert(not fact.windows_capture_busy and events[#events] == "shot_cancelled")
reject = true
begin("display")
assert(not fact.windows_capture_busy and events[#events] == "shot_cancelled")
reject = false
begin("display")
complete("screenshot.freeze", 9)
complete("screenshot.finish", { path = "C:/Imágenes/Marea/photo.png", clipboard = false, clipboard_error = "busy" })
assert(not fact.windows_capture_busy and events[#events] == "shoot")
assert(text.windows_capture_path == "C:/Imágenes/Marea/photo.png" and notices[#notices]:find("guardada"))
assert(#requests == 0)
log("PASS: capture cancellation, native errors, queue failure, duplicate event and partial clipboard success")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: capture cancellation', 'capture')
