"""Regression coverage for row reuse, wardrobe slots, folding and search ranking."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
generated = (root / 'marea-desktop.luau').read_text(encoding='utf-8')
scene = (root / 'marea-desktop.plm').read_text(encoding='utf-8')
assert 'on press row_zone.$k { emit resolve(k) }' not in scene
assert 'opacity: rise.$k * (1 - abs(flung.$k))' in scene
assert 'on change windows_row_revision.$k' in scene
assert 'and not windows_shelf_folded' in scene
render = generated.split('local windows_row_keys, windows_row_serial', 1)[1].split('--  One arrives:', 1)[0]
render = 'local windows_row_keys, windows_row_serial' + render
counts = generated.split('local function cap_counts()', 1)[1].split('--  The scene counts', 1)[0]
counts = 'local function cap_counts()' + counts
refill = generated.split('local function refill(force)', 1)[1].split('on("fact:tray_open"', 1)[0]
refill = 'local function refill(force)' + refill
checks = r'''
local fact, text = {}, {}
local rows, finished, snoozed, notices, requests = {}, {}, {}, {}, {}
local live = {}
local CATEGORY_OF = { SYSTEM = 4 }
local function classify() return 4 end
local function tr(s) return s end
local function shown(_, s) return s end
local function notification_age() return "now" end
local function row_of(n) return {id=n.id, cat=4, app="SYSTEM", title="Owned notice", detail="Test"} end
local function remove_done()
    for i = #rows, 1, -1 do if rows[i].done then finished[rows[i].id] = true; table.remove(rows, i) end end
end
local function refresh_preview() end
local function notice(error) notices[#notices + 1] = error end
local reject = false
local native_sys = {call_async = function(name, args, done)
    assert(name == "notifications.dismiss")
    if reject then error("queue full") end
    requests[#requests + 1] = {id=args[1], done=done}
end}
__RENDER__
__COUNTS__
__REFILL__
__DISMISS__
for id = 1, 8 do live[id] = {id=id} end
for id = 1, 5 do rows[id] = row_of(live[id]) end
fact.tray_open = true; fact["n.4"] = 8
render()
local revision = fact["windows_row_revision.1"]
rows[1].done = true; render()
assert(not fact["alive.1"], "refresh revived a dismissed notification")
assert(revision == fact["windows_row_revision.1"])
dismiss_native(1); dismiss_native(1); assert(#requests == 1)
requests[1].done("", 0)
assert(#rows == 5 and #live == 7 and fact["n.4"] == 7)
assert(fact["alive.1"] and fact["windows_row_revision.1"] > revision)
local failed = rows[1].id
rows[1].done = true; fact["n.4"] = 6
dismiss_native(failed)
-- Force reuse before a rejected command returns: restore by identity, not slot.
refill(true)
requests[2].done("denied", 1)
assert(not finished[failed] and fact["n.4"] == 7 and #notices == 1)
for _, row in ipairs(rows) do assert(not row.done) end
reject = true; rows[1].done = true; dismiss_native(rows[1].id)
assert(not rows[1].done and #notices == 2)

do
    local settings = {wears={hat=true, phones=true, glasses=true, mug=true}, shelf_folded=true}
    local PIECES = {"hat", "glasses", "mug", "phones"}
    local handlers, saves = {}, 0
    local function on(key, fn) handlers[key] = fn end
    local function save_settings() saves += 1 end
    __WARDROBE__
    assert(not fact["wears.hat"] and fact["wears.phones"])
    assert(fact["wears.glasses"] and fact["wears.mug"] and fact.windows_shelf_folded)
    fact["wears.hat"] = true; handlers["fact:wears.hat"](true)
    assert(fact["wears.hat"] and not fact["wears.phones"])
    fact["wears.phones"] = true; handlers["fact:wears.phones"](true)
    assert(not fact["wears.hat"] and fact["wears.phones"])
    handlers["fact:windows_shelf_folded"](false); assert(saves == 3)
end
do
    local matcher = (function() __MATCH__ end)()
    assert(matcher.fold("ÁÉÍÓÚÜÑÇ") == "aeiouunc")
    assert(matcher.score("Canción del verano.txt", "verano cancion"))
    assert(matcher.score("CAFE" .. utf8.char(0x301) .. ".txt", "café"))
    assert(matcher.score("Visual Studio Code", "vsc"))
    assert(matcher.score("Spotify", "spotfy"))
    assert(matcher.score("日本語.txt", "日本語"))
    assert(not matcher.score("cat", "bat"))
    assert(not matcher.score("Spotify", "spotszzz"))
    assert(matcher.score("Spotify", "spotify") > matcher.score("Spotify", "spotfy"))
end
do
    local search_match = (function() __MATCH__ end)()
    local apps, OWN, open_windows, hooks, model = {}, {}, {}, {}, {}
    local generation, home_dir = 0, "C:/owned"
    local deferred, replies = {}, {}
    local function after(_, fn) deferred[#deferred + 1] = fn end
    local sys = {ask_async = function(_, _, fn) replies[#replies + 1] = fn end}
    local function prefer(a, b) return a.name < b.name end
    local function paint(_, list) model.results = table.clone(list); fact.selected = 0 end
    for i = 1, 8 do apps[i] = {name="Alpha " .. i, exec="app" .. i} end
    __SEARCH__
    text.query = "alpha"; search(); assert(#model.results == 7)
    fact.selected = 2; deferred[1]()
    replies[1]({items={{name="Alpha file",path="C:/owned/alpha.txt"}},truncated=true})
    assert(#model.results == 5 and model.results[5].filepath and fact.selected == 2)
    assert(text.windows_search_status:find("Partial",1,true))
    text.query = "alpha"; search(); deferred[2]()
    text.query = "newer"; search()
    replies[2]({items={{name="Stale file",path="C:/owned/stale.txt"}}})
    assert(#model.results == 0, "late search callback replaced a newer query")
end
log("PASS: dismissed-row refresh/reuse, failed dismissal recovery/counts, exclusive head slot, folding persistence, accented/token/typo search")
'''
for marker, value in [('RENDER', render), ('COUNTS', counts), ('REFILL', refill),
                      ('DISMISS', (root / 'windows/notification-dismiss.luau').read_text(encoding='utf-8')),
                      ('WARDROBE', (root / 'windows/wardrobe.luau').read_text(encoding='utf-8')),
                      ('MATCH', (root / 'windows/search-match.luau').read_text(encoding='utf-8')),
                      ('SEARCH', (root / 'windows/search.luau').read_text(encoding='utf-8'))]:
    checks = checks.replace('__' + marker + '__', value)
run_checks(args, checks, 'PASS: dismissed-row', 'desktop-controls')
