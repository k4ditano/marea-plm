"""Test device latency, coalescing and failure with the real Luau runtime.

Only the native services are mocked: this never changes hardware settings.
"""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description=__doc__)
from logic_test import runner_arguments, run_checks
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('level-controls.luau').read_text(encoding='utf-8')
checks = '''
local now, timers, handlers, watches, calls, notices = 0, {}, {}, {}, {}, {}
local fact = {}
local next_timer = 0
local function after(ms, callback)
    next_timer += 1
    table.insert(timers, { id = next_timer, at = now + ms, callback = callback })
    return next_timer
end
local function cancel(id)
    for k = #timers, 1, -1 do if timers[k].id == id then table.remove(timers, k) end end
end
local function on(name, callback) handlers[name] = callback end
local native = {
    watch = function(name, callback) watches[name] = callback end,
    call_async = function(name, values, callback) table.insert(calls, { name = name, value = values[1], callback = callback }) end,
}
local function advance(ms)
    local until_time = now + ms
    while true do
        table.sort(timers, function(a, b) return a.at < b.at end)
        if not timers[1] or timers[1].at > until_time then break end
        local timer = table.remove(timers, 1)
        now = timer.at; timer.callback()
    end
    now = until_time
end
local install = (function()
__MODULE__
end)()
install(native, function(message) table.insert(notices, message) end)
local function drag(k, value)
    fact["windows_level_drag." .. k] = true
    fact["windows_level_pending." .. k] = true
    handlers[({ [0] = "set_brightness", "set_volume", "set_mic" })[k]](value)
end
local function release(k)
    fact["windows_level_drag." .. k] = false
    handlers["fact:windows_level_drag." .. k]()
end
-- Startup has not observed an output device yet.
drag(1, 0.8); advance(16); release(1)
assert(#calls == 0 and not fact["windows_level_pending.1"], "unobserved output received a command")
watches.brightness({ present = true, level = 0.5 })
watches.audio({ volume = 0.4 })
for i = 1, 100 do drag(0, i / 100) end
advance(80)
assert(#calls == 1 and calls[1].value == 1, "drag burst was not coalesced")
for i = 1, 65 do drag(0, i / 100) end
advance(1000)
assert(#calls == 1, "a slow device accumulated calls")
watches.brightness({ present = true, level = 1 })
calls[1].callback("", 0)
assert(fact["windows_level_pending.0"], "stale acknowledgement cleared latest preview")
advance(80)
assert(#calls == 2 and calls[2].value == 0.65, "the final drag value was lost")
release(0)
watches.brightness({ present = true, level = 0.65 })
calls[2].callback("", 0)
assert(not fact["windows_level_pending.0"], "actual device confirmation did not settle")
drag(1, 0.8); advance(16); release(1)
calls[3].callback("driver error", -1)
assert(not fact["windows_level_pending.1"] and notices[#notices]:find("driver error"), "driver failure was hidden")
drag(1, 0.9); advance(16); release(1)
calls[4].callback("", 0)
advance(3501)
assert(not fact["windows_level_pending.1"] and notices[#notices]:find("confirmado"), "unconfirmed values stayed fabricated")
drag(1, 0.4); advance(16); release(1); calls[5].callback("", 0)
advance(32)
fact["windows_level_pending.1"] = true
handlers["fact:windows_level_drag.1"]()
advance(32)
assert(not fact["windows_level_pending.1"])
handlers.set_volume(0.6)
assert(fact["windows_level_pending.1"], "release settled a newer preview before its request arrived")
advance(16); calls[6].callback("", 0); watches.audio({ volume = 0.6 })
assert(not fact["windows_level_pending.1"])
watches.brightness({ present = false, error = "monitor removed" })
drag(0, 0.7)
assert(not fact["windows_level_pending.0"] and notices[#notices] == "monitor removed")
assert(#calls == 6, "unavailable monitor received a call")
-- The upstream microphone slider has its own pending state and confirmation.
watches.audio({ volume = 0.6, input = 0.5 })
drag(2, 0.7); advance(16)
assert(calls[7].name == "audio.input" and calls[7].value == 0.7)
release(2); calls[7].callback("", 0)
assert(fact["windows_level_pending.2"], "microphone settled without readback")
watches.audio({ volume = 0.6, input = 0.7 })
assert(not fact["windows_level_pending.2"])
watches.audio({ volume = 0.6 })
drag(2, 0.8); advance(100)
assert(#calls == 7 and not fact["windows_level_pending.2"], "missing microphone received a call")
-- Internal panels may expose only discrete brightness steps. The preview
-- stays smooth, but confirmation must compare with the nearest real step.
watches.brightness({ present = true, level = 0.5, levels = { 0.1, 0.3, 0.5, 0.7, 1.0 } })
drag(0, 0.62); advance(80); release(0)
assert(calls[8].value == 0.7, "brightness did not select a supported panel level")
calls[8].callback("", 0)
watches.brightness({ present = true, level = 0.7, levels = { 0.1, 0.3, 0.5, 0.7, 1.0 } })
assert(not fact["windows_level_pending.0"], "a confirmed discrete level did not settle")
-- Losing a device cancels an unsent value, including a timer already queued.
drag(1, 0.8)
watches.audio({})
advance(16); release(1)
assert(#calls == 8 and not fact["windows_level_pending.1"], "removed output kept an unsent value")
assert(not fact["windows_level_available.1"] and not fact["windows_level_available.2"])
-- An OS call already in progress cannot be revoked. Its later reply must not
-- replay an old queued value onto a newly attached default output.
watches.audio({ volume = 0.2, input = 0.3 })
assert(fact["windows_level_available.1"] and fact["windows_level_available.2"])
drag(1, 0.9); advance(16)
assert(#calls == 9)
drag(1, 0.75)
watches.audio({})
watches.audio({ volume = 0.25 })
calls[9].callback("device removed", -1)
advance(100); release(1)
assert(#calls == 9 and not fact["windows_level_pending.1"], "stale value reached replacement output")
drag(1, 0.4); advance(16); release(1)
assert(calls[10].value == 0.4, "fresh gesture after reconnect was lost")
calls[10].callback("", 0); watches.audio({ volume = 0.4 })
assert(not fact["windows_level_pending.1"])
-- Invalid observations must not keep a percentage or enable native writes.
watches.audio({ volume = 0/0, input = "unknown" })
drag(1, 0.5); drag(2, 0.5); advance(100)
assert(#calls == 10 and not fact["windows_level_available.1"] and not fact["windows_level_available.2"])
watches.audio({ volume = 0.4 })
drag(1, 0.65); advance(16); release(1)
assert(#calls == 11)
advance(4501)
assert(not fact["windows_level_pending.1"] and notices[#notices]:find("respondido"), "unanswered native command kept a fabricated preview")
assert(not fact["windows_level_available.1"], "hung track remained interactive")
watches.audio({ volume = 0.4 })
assert(not fact["windows_level_available.1"], "polling reopened the track before the command returned")
drag(1, 0.7); advance(100); release(1)
assert(#calls == 11 and not fact["windows_level_pending.1"], "hung worker accumulated commands")
calls[11].callback("", 0)
assert(fact["windows_level_available.1"], "returned command did not reenable its track")
advance(100)
assert(#calls == 11 and not fact["windows_level_pending.1"], "late callback replayed a discarded gesture")
drag(1, 0.3); advance(16); release(1)
assert(calls[12].value == 0.3, "responsive worker did not allow a fresh retry")
calls[12].callback("", 0); watches.audio({ volume = 0.3 })
assert(not fact["windows_level_pending.1"])
-- A sustained fast drag must not retain a timeout closure for every command.
advance(5000)
for i = 1, 200 do
    drag(1, (i % 90) / 100)
    advance(16)
    calls[#calls].callback("", 0)
    assert(#timers <= 3, "slider accumulated expired command/confirmation watchdogs")
end
release(1)
watches.audio({ volume = 0.2 })
advance(100)
assert(#timers == 0, "confirmed slider retained watchdogs")
log("PASS: coalesced sliders, stale callbacks, failures, device confirmation, timeout and unavailable hardware")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: coalesced sliders', 'levels')
