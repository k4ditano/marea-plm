"""Current six-card library in real Luau, with native boundaries mocked."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks
parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
logic = (root / 'marea-desktop.luau').read_text(encoding='utf-8')
start = logic.index('local function deriva()\n')
end = logic.index('\nend\nderiva()', start) + len('\nend\nderiva()')
checks = r'''
local fact, text, model, events, timers, pending, queries, commands, children, written = {page = "drift"}, {}, {}, {}, {}, {}, {}, {}, {}, {}
local hooks = {language = {}}
local serial, encoded = 0, {}
local json = {
    encode = function(v) serial += 1; encoded[tostring(serial)] = v; return tostring(serial) end,
    decode = function(s) return assert(encoded[s], "invalid fixture JSON") end,
}
local function tr(s) return s end
local function day_label(n) return tostring(n) end
local function on(name, f) events[name] = f end
local function fire(name, ...) assert(events[name], name)(...) end
local function emit(name) assert(name == "say_toast" or name == "drift_saved") end
local function after(ms, f) local timer = {ms = ms, f = f}; table.insert(timers, timer); return timer end
local function cancel(t) t.cancelled = true end
local function kill() end
local function log() end
local function native_run(command, args, done, options)
    assert(command == "deriva-worker" or command == "node", command)
    assert(options.cwd == ".")
    pending[#pending + 1] = {command = command, args = args, done = done}
end
local function native_spawn(command, args, line, exit, options)
    assert(command == "deriva-worker" and args[1] == "stdio" and options.stdin == "open")
    children[#children + 1] = {line = line, exit = exit}; return #children
end
local function write(id, data)
    table.insert(written, {id = id, value = encoded[data:match("^(%d+)")]}); return true
end
local native_sys = {
    ask_async = function(name, args, done) table.insert(queries, {name = name, args = args, done = done}) end,
    call_async = function(name, args, done) table.insert(commands, {name = name, args = args, done = done}) end,
}
local sys = {ask = function() return "copied text" end}
local function run(command, args, done) assert(command == "xdg-open"); table.insert(commands, {name = command, args = args, done = done}) end
__MODULE__
local function take(method)
    for _, p in ipairs(pending) do
        if not p.used and p.command == "deriva-worker" and (p.args[1] == method or (p.args[1] == "call" and p.args[2] == method)) then
            p.used = true; return p
        end
    end
    error("No pending " .. method)
end
local function answer(p, result, error)
    p.done(json.encode(error and {ok = false, error = {message = error}} or {ok = true, result = result}), error and 1 or 0)
end
local function params(p) return encoded[p.args[4]] end
local function item(i)
    return {id = "capture" .. i, type = "text", title = "Title " .. i, excerpt = string.rep("ñ海", 150), captured_at = 1700000000000, spaces = {}, favorite = i == 2}
end
local items = {}; for i = 1, 10 do items[i] = item(i) end
local folders = {{kind = "space", id = "inspiracion", name = "inspiracion", count = 2},
    {kind = "space", id = "custom", name = "My folder", count = 1}, {kind = "today", count = 3}}
local function home(list, sections) return {items = list or items, stats = {captures = 10, trashed = 2}, sections = sections or folders} end
answer(take("where"), {blobs = "C:/Library ñ/blobs"})
answer(take("home"), home())
assert(fact.windows_deriva_loaded and not fact.windows_deriva_busy and #model.drift == 6)
assert(model.drift[1].title == "Title 1" and utf8.len(model.drift[1].excerpt) == 220)
assert(fact["drift.kept"] == 10 and fact["drift.trashed"] == 2 and #model.drift_chips == 5)
fire("drift_scroll", -1); assert(model.drift[1].title == "Title 4" and #model.drift == 6)
fire("drift_scroll", -1); assert(model.drift[1].title == "Title 7" and #model.drift == 4)
fire("drift_scroll", -1); assert(model.drift[1].title == "Title 7")
fire("drift_scroll", 1); fire("drift_scroll", 1)

fire("drift_fav", 0)
assert(model.drift[1].fav and model.drift_chips[3].label == "★  2")
local favourite = take("annotate"); assert(params(favourite).id == "capture1")
local count = #pending; fire("drift_fav", 0); assert(#pending == count)
answer(favourite, nil, "write failed")
assert(not model.drift[1].fav and model.drift_chips[3].label == "★  1")
fire("drift_move", 0); assert(model.drift_spaces[1].name == "Inspiration")
fire("drift_to", 1); local move = take("annotate")
assert(params(move).space == "custom" and params(move).id == "capture1")
answer(move, {id = "capture1"}); answer(take("home"), home())
fire("drift_bin", 0); local trash = take("trash"); assert(params(trash).id == "capture1")
answer(trash, {id = "capture1"}); answer(take("home"), home())
fire("drift_bin_view"); local bin = take("home"); assert(params(bin).trashed)
answer(bin, home({items[1]})); assert(fact["drift.trash"])
fire("drift_bin", 0); answer(take("untrash"), {id = "capture1"}); answer(take("home"), home({items[1]}))
fire("drift_bin_view"); answer(take("home"), home())

-- An older home response cannot change counts during a search debounce.
fire("drift_open"); local stale = take("home")
text.drift_q = "first"; fire("text:drift_q")
answer(stale, {items = {}, stats = {captures = 999, trashed = 0}, sections = {}})
assert(fact["drift.kept"] == 10 and #model.drift == 6)
timers[#timers].f(); assert(#written == 1)
text.drift_q = "second"; fire("text:drift_q")
local debounce = timers[#timers]
children[1].line(json.encode({ok = true, id = written[1].value.id, result = {items = {item(88)}}}))
assert(model.drift[1].title == "Title 1")
debounce.f(); assert(#written == 2)
children[1].line(json.encode({ok = true, id = written[2].value.id, result = {items = {item(99)}}}))
assert(#model.drift == 1 and model.drift[1].title == "Title 99")
text.drift_q = ""; fire("drift_open"); answer(take("home"), nil, "database unavailable")
assert(#model.drift == 1 and text.windows_deriva_status:find("database unavailable", 1, true))
fire("drift_open"); answer(take("home"), home())
fire("drift_pick", 0); take("annotate")
answer(take("get"), {item = items[1], text = "Whole note ñ 海\n\nhttps://example.test"})
assert(commands[#commands].name == "clipboard.set" and commands[#commands].args[1]:find("\n\n", 1, true))
commands[#commands].done("clipboard locked", 1); assert(text.windows_deriva_status:find("Could not copy", 1, true))
fire("drift_pick", 0); take("annotate"); answer(take("get"), nil, "not readable")
assert(#commands == 1)

local prose = "# Heading\n\n  Keep indentation\nhttps://example.test/page\n"
fire("drop:drift_drop", prose, "text/plain")
local drop = take("ingest"); local request = encoded[drop.args[3]]
assert(request.type == "text" and request.text == prose)
answer(drop, {saved = 1}); answer(take("home"), home())
fire("drop:drift_later", "# uri comment\r\nfile:///C:/Pictures%20%C3%B1/%E6%B5%B7.png\r\nfile:///C:/bad%GG\r\nhttps://example.test/", "text/uri-list")
local first, second = take("ingest"), take("ingest")
local file = encoded[first.args[3]].paths and first or second
assert(encoded[file.args[3]].paths[1] == "C:/Pictures ñ/海.png" and encoded[file.args[3]].space == "leer-luego")
answer(first, {saved = 1}); answer(second, {failed = 1})
assert(fact["drift.result"] == 3 and text["drift.toast"] == "Saved: 1 · Already kept: 0 · Failed: 2")
answer(take("home"), home())

-- Only one image converter is in flight, following the visible page.
for _, it in ipairs(items) do it.type = "image"; it.blob_path = "C:/Pictures/" .. it.id .. ".png" end
items[4].source_url = [[file://\\?\C:\Saved ñ\photo #1%.png]]
fire("drift_open"); answer(take("home"), home())
assert(#queries == 1 and queries[1].name == "images.thumbnail")
assert(queries[1].args[2] == 288 and queries[1].args[3] == 168 and queries[1].args[4] == "crop")
fire("drift_scroll", -1)
assert(model.drift[1].link == "C:/Saved ñ/photo #1%.png")
queries[1].done("C:/cache/one.jpg")
assert(not model.drift[1].has_thumb and #queries == 2 and queries[2].args[1]:find("capture4", 1, true))
queries[2].done("C:/cache/four.jpg"); assert(model.drift[1].has_thumb)
fact.page = "home"; queries[3].done(nil, "unsupported image"); assert(#queries == 3)
print("PASS: modern Deriva: six cards, folders, favourites with rollback, trash/restore, stale query rejection, errors, Unicode notes/drops and serial visible covers")
'''.replace('__MODULE__', logic[start:end])
run_checks(args, checks, 'PASS: modern Deriva', 'deriva library')
