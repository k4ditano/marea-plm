"""Bounded per-session mixer gestures with actual Luau and isolated native fakes."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('app-audio.luau').read_text(encoding='utf-8')
checks = '''
local now, next_id, timers, calls, notices, paints = 0, 0, {}, {}, {}, 0
local function after(ms, callback)
    next_id += 1
    timers[next_id] = { at = now + ms, callback = callback }
    return next_id
end
local function cancel(id) timers[id] = nil end
local function advance(ms)
    local until_time = now + ms
    while true do
        local id, at = nil, math.huge
        for k, t in pairs(timers) do if t.at < at then id, at = k, t.at end end
        if not id or at > until_time then break end
        local timer = timers[id]; timers[id] = nil; now = at; timer.callback()
    end
    now = until_time
end
local native = { call_async = function(name, args, done)
    calls[#calls + 1] = { name = name, id = args[1], value = args[2], done = done }
end }
local install = (function()
__MODULE__
end)()
local mixer = install(native, function(message) notices[#notices + 1] = message end, function() paints += 1 end)
local function rows(v, muted, second)
    local r = { { id = "same-pid-instance-ñ", volume = v, muted = muted == true } }
    if second then r[2] = { id = "same-pid-instance-日本語", volume = 0.7, muted = false } end
    return r
end
local first, second = "same-pid-instance-ñ", "same-pid-instance-日本語"
assert(not mixer.volume(first, 0.5), "an unobserved session received a command")
mixer.observe(rows(0.3, false, true))
for i = 1, 100 do mixer.volume(first, i / 100) end
advance(16)
assert(#calls == 1 and calls[1].id == first and calls[1].value == 1)
for i = 1, 65 do mixer.volume(first, i / 100) end
advance(1000)
assert(#calls == 1, "slow session accumulated native commands")
mixer.volume(second, 0.45); advance(16)
assert(#calls == 2 and calls[2].id == second, "one slow session blocked the other")
calls[2].done("", 0)
mixer.observe({ { id = first, volume = 1, muted = false }, { id = second, volume = 0.45, muted = false } })
calls[1].done("", 0); advance(16)
assert(#calls == 3 and calls[3].value == 0.65 and calls[3].id == first)
assert(mixer.preview(first, 1, false) == 0.65, "old readback overwrote the latest gesture")
calls[3].done("", 0)
mixer.observe(rows(0.65, false, true))
assert(mixer.preview(first, 0.66, false) == 0.66, "confirmed preview did not retire")

-- Explicit mute values serialize with levels and preserve the user's final intent.
mixer.mute(first); advance(16)
assert(calls[4].name == "audio.app_mute" and calls[4].value == true)
mixer.volume(first, 0.4)
calls[4].done("", 0); advance(16)
assert(calls[5].name == "audio.app_volume" and calls[5].value == 0.4)
calls[5].done("", 0); mixer.observe(rows(0.4, true))
local v, muted = mixer.preview(first, 0.4, true)
assert(v == 0.4 and muted)
mixer.mute(first); mixer.mute(first); advance(16)
assert(calls[6].value == true, "repeated mute gestures lost their final intent")
calls[6].done("", 0); mixer.observe(rows(0.4, true))

-- Errors and missing acknowledgements restore actual values instead of lying.
mixer.volume(first, 0.9); advance(16); calls[7].done("driver rejected", -1)
assert(mixer.preview(first, 0.4, true) == 0.4 and notices[#notices] == "driver rejected")
mixer.volume(first, 0.8); advance(16); calls[8].done("", 0); advance(3501)
assert(mixer.preview(first, 0.4, true) == 0.4 and notices[#notices]:find("confirmed"))

-- Closing a stream cancels unsent work. Same executable/PID is not an identity.
mixer.volume(first, 0.6); mixer.observe({ { id = second, volume = 0.7, muted = false } }); advance(16)
assert(#calls == 8)
mixer.volume(second, 0.2); advance(16)
mixer.volume(second, 0.3); mixer.observe({})
mixer.observe(rows(0.4, true)); calls[9].done("late error", -1); advance(100)
assert(#calls == 9 and not mixer.volume(second, 0.5))
assert(mixer.preview(first, 0.4, true) == 0.4)

-- Hung calls remain serialized, but stop presenting an invented level.
mixer.volume(first, 0.1); advance(16); advance(4501)
assert(not mixer.volume(first, 0.8) and mixer.preview(first, 0.4, true) == 0.4)
calls[10].done("", 0); advance(100)
assert(#calls == 10 and mixer.volume(first, 0.5))
advance(16); calls[11].done("", 0); mixer.observe(rows(0.5, true))
for _, invalid in ipairs({ -1, 2, 0/0, math.huge, "0.5" }) do assert(not mixer.volume(first, invalid)) end
advance(5000)
assert(#calls == 11 and next(timers) == nil, "settled mixer kept background timers")
log("APP_AUDIO_OK: independent instance IDs, bounded bursts, final values, mute, failures, removal and idle cleanup")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'APP_AUDIO_OK', 'app audio')
