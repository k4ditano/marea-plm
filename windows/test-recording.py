"""Exercise asynchronous recorder ownership and completion in isolated Luau."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('recording.luau').read_text(encoding='utf-8')
checks = r'''
local fact, text, handlers, requests, events, notices, timers = {}, {}, {}, {}, {}, {}, {}
local reject = false
local function on(name, callback) handlers[name] = callback end
local function emit(name) events[#events + 1] = name; if name == "stop" then fact.face = "eye"; handlers.stop() end end
local function notice(message) notices[#notices + 1] = message end
local function after(_, callback) timers[#timers + 1] = callback end
local calls = {}
local function perform(name, arg) calls[#calls + 1] = { name, arg } end
local native_sys = { ask_async = function(name, args, callback)
    if reject then error("queue full") end
    requests[#requests + 1] = { name = name, args = args, callback = callback }
end }
local function complete(name, value, error)
    local request = table.remove(requests, 1)
    assert(request and request.name == name, "unexpected request: " .. name)
    request.callback(value, error)
end
local function tick() local callback = table.remove(timers, 1); assert(callback); callback() end
__MODULE__
local function begin()
    fact.face = "rec"; fact.nook_screen = 1; text["screen.1.name"] = "display two"
    handlers["fact:face"]("rec")
end
-- Cancelling before the native start returns still stops that exact recorder.
begin()
handlers["fact:face"]("rec")
assert(#requests == 1 and requests[1].args[1] == "display two")
emit("stop")
complete("recording.start", { state = "recording" })
assert(not fact.taping and fact.windows_recording_busy)
complete("recording.stop", { state = "recording" })
tick(); complete("recording.state", { state = "finalizing" })
assert(#events == 1 and fact.windows_recording_busy)
tick(); complete("recording.state", { state = "saved", frames = 12, path = "C:\\Vídeos\\海 test.mp4" })
assert(not fact.windows_recording_busy and text["reel.name"] == "海 test.mp4")
assert(events[#events] ~= "recorded", "celebration happened before completion delay")
tick(); assert(events[#events] == "recorded")
handlers.reel_copy(); assert(calls[#calls][1] == "clipboard.set")
handlers.reel_watch(); assert(calls[#calls][1] == "shell.open")
-- A running encoder failure never displays a saved card.
begin(); complete("recording.start", { state = "recording" }); assert(fact.taping)
local count = #events
tick(); complete("recording.state", { state = "error", error = "device removed", path = "partial.mp4" })
assert(not fact.windows_recording_busy and not fact.taping and #events == count + 1)
assert(notices[#notices]:find("partial.mp4"))
-- Failure/timeout during start and command queue rejection remain retryable.
begin(); complete("recording.start", nil, "startup timeout")
assert(not fact.windows_recording_busy and not fact.taping)
reject = true; begin(); assert(not fact.windows_recording_busy)
reject = false; begin(); complete("recording.start", { state = "recording" })
emit("stop"); emit("stop"); assert(#requests == 1)
complete("recording.stop", nil, "transient failure")
tick(); complete("recording.stop", { state = "finalizing" })
complete("recording.state", { state = "cancelled" })
assert(not fact.windows_recording_busy and #requests == 0 and #timers == 0)
-- Losing a poll/stop queue slot must not abandon a recording still running.
begin(); complete("recording.start", { state = "recording" })
reject = true; tick()
assert(fact.windows_recording_busy and not fact.taping and #timers == 1)
reject = false; tick(); complete("recording.stop", { state = "finalizing" })
complete("recording.state", { state = "finalizing" })
tick(); complete("recording.state", { state = "cancelled" })
assert(not fact.windows_recording_busy and #requests == 0 and #timers == 0)
log("PASS: recording cancellation, duplicate start/stop, finalized-only saved card, errors and retry")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: recording cancellation', 'recording')
