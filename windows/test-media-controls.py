"""Check asynchronous media state/command ownership without controlling a player."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('media-controls.luau').read_text(encoding='utf-8')
checks = r'''
local fact, text, model, handlers, timers, notices, commands, queries = {}, {}, {}, {}, {}, {}, {}, {}
local listener, reject_command, reject_query
local function tr(value) return value end
local function on(name, callback) handlers[name] = callback end
local function after(_, callback) timers[#timers + 1] = callback end
local function notice(value) notices[#notices + 1] = value end
local function install_media_volume() return function() end end
local install = (function() __MODULE__ end)()
install({
    watch = function(name, callback) assert(name == "media"); listener = callback; return true end,
    call_async = function(name, args, callback)
        if reject_command then error("queue full") end
        commands[#commands + 1] = {name = name, args = args, done = callback}
    end,
    ask_async = function(name, args, callback)
        assert(name == "media.state")
        if reject_query then error("query queue full") end
        queries[#queries + 1] = callback
    end,
}, notice)
local function state(player, playing, can_next)
    return {available = true, player = player, playing = playing, can_toggle = true,
            can_previous = false, can_next = can_next, error = ""}
end
assert(not fact.windows_media_available and not fact.windows_media_can_toggle)
local covered = state("spotify-fixture", true, true); covered.art = "C:/covers/track ñ.png"
listener(covered)
assert(fact.windows_media_has_art and model.windows_media_cover[1].pic == covered.art)
local same = model.windows_media_cover; listener(covered); assert(model.windows_media_cover == same)
listener(state("owned-player", false, true))
assert(not fact.windows_media_has_art and #model.windows_media_cover == 0, "stale artwork survived a new track")
assert(fact.windows_media_available and fact.windows_media_can_toggle)
assert(not fact.windows_media_can_previous and fact.windows_media_can_next)
handlers.previous(); assert(#commands == 0)
handlers.play_pause(); handlers.play_pause(); handlers.next()
assert(#commands == 1 and commands[1].name == "media.toggle")
assert(commands[1].args[1] == "owned-player" and fact.windows_media_busy)
assert(not fact.windows_media_can_toggle and not fact.windows_media_can_next)
commands[1].done("", 0); assert(#queries == 1 and fact.windows_media_busy)
queries[1](state("owned-player", true, false), nil)
assert(not fact.windows_media_busy and not fact.windows_media_can_next)
handlers.play_pause()
listener(state("another-player", false, true))
commands[2].done("late failure", -1)
assert(#queries == 1 and #notices == 0 and not fact.windows_media_busy)
handlers.next(); commands[3].done("declined", -1)
assert(#notices == 1 and #queries == 2)
listener(state("another-player", false, false))
queries[2](state("another-player", true, true), nil)
assert(not fact.windows_media_can_next, "a stale query replaced a newer subscription")
reject_command = true; reject_query = true
handlers.play_pause()
assert(not fact.windows_media_busy and not fact.windows_media_available)
assert(#notices == 3 and text.windows_media_status == "Reproductor no disponible")
reject_command = false; reject_query = false
listener(state("owned-player", true, true))
handlers.next(); local pending = commands[#commands]
timers[#timers]()
assert(not fact.windows_media_busy and notices[#notices]:find("tiempo"))
local notices_before, queries_before = #notices, #queries
pending.done("late", -1)
assert(#notices == notices_before and #queries == queries_before)
listener({available = false, player = "", error = ""})
assert(not fact.windows_media_available and text.windows_media_status == "Nothing playing")
install({watch = function() return false end}, notice)
assert(not fact.windows_media_available and notices[#notices]:find("no está disponible"))
log("PASS: native media capabilities, paused session, async deduplication, player changes, stale queries, failure and timeout")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: native media capabilities', 'media-controls')
