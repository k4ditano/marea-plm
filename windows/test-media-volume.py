"""Check player volume coalescing and isolation without changing desktop audio."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('media-volume.luau').read_text(encoding='utf-8')
checks = r'''
local fact, text, handlers, notices, timers, commands, queries = {}, {}, {}, {}, {}, {}, {}
local now, reject = 0, false
local function tr(s) return s end
local function on(key, fn) handlers[key] = fn end
local function notice(s) notices[#notices + 1] = s end
local function after(ms, fn) timers[#timers + 1] = {due=now+ms, fn=fn} end
local function advance(ms)
    now += ms
    local again = true
    while again do
        again = false
        for i, t in ipairs(timers) do
            if t.due <= now then table.remove(timers, i); t.fn(); again = true; break end
        end
    end
end
local install = (function() __MODULE__ end)()
local observe = install({
    call_async = function(name, args, fn)
        assert(name == "media.volume")
        if reject then error("queue full") end
        commands[#commands+1] = {player=args[1], value=args[2], done=fn}
    end,
    ask_async = function(name, args, fn) assert(name == "media.state"); queries[#queries+1] = fn end,
}, notice)
local function state(player, level)
    return {available=true, player=player, can_volume=true, volume=level}
end
observe(state("a", .4)); assert(fact.windows_media_can_volume and fact.windows_media_volume == .4)
for n = 1, 100 do handlers.windows_set_media_volume(n / 100) end
advance(16)
assert(#commands == 1 and commands[1].value == 1 and commands[1].player == "a")
handlers.windows_set_media_volume(.2); handlers.windows_set_media_volume(.3)
advance(30); assert(#commands == 1, "concurrent writes piled up")
commands[1].done("", 0); advance(16)
assert(#commands == 2 and commands[2].value == .3 and #queries == 0)
commands[2].done("", 0); assert(#queries == 1)
queries[1](state("a", .3))
assert(not fact.windows_media_volume_pending and fact.windows_media_volume == .3)
handlers.windows_set_media_volume(.8); advance(16)
observe(state("b", .5))
commands[3].done("old failure", 1)
assert(#notices == 0 and fact.windows_media_volume == .5)
handlers.windows_set_media_volume(.2); advance(16)
commands[4].done("denied", 1)
assert(#notices == 1 and not fact.windows_media_volume_pending)
reject = true; handlers.windows_set_media_volume(.1); advance(16)
assert(#notices == 2 and not fact.windows_media_volume_pending)
reject = false; handlers.windows_set_media_volume(.9); advance(16)
local pending = commands[#commands]
advance(4501)
assert(not fact.windows_media_can_volume and not fact.windows_media_volume_pending)
local count = #commands; handlers.windows_set_media_volume(.5); advance(16); assert(#commands == count)
pending.done("", 0); assert(fact.windows_media_can_volume)
observe({available=true, player="unknown", can_volume=false})
assert(not fact.windows_media_can_volume)
handlers.windows_set_media_volume(.1); advance(16); assert(#commands == count)
log("PASS: per-player volume, 100-step coalescing, latest value, readback, player changes, command failure and bounded timeout")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: per-player volume', 'media-volume')
