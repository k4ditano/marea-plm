"""Exercise bounded persistent search and retirement in real Luau, without a model."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
source = Path(__file__).with_name('deriva-search.luau').read_text(encoding='utf-8')
checks = r'''
local serialized, serial, timers, workers, written, killed, results = {}, 0, {}, {}, {}, {}, {}
local json = {
    encode = function(v) serial += 1; serialized[tostring(serial)] = v; return tostring(serial) end,
    decode = function(s) return assert(serialized[s]) end,
}
local function after(ms, f) local t = {ms = ms, f = f}; table.insert(timers, t); return t end
local function cancel(t) t.cancelled = true end
local function kill(id) table.insert(killed, id) end
local function write(id, value) table.insert(written, {id = id, value = serialized[value:match('^(%d+)')]}); return true end
local function spawn(command, args, line, exit, options)
    assert(command == "deriva-worker" and args[1] == "stdio" and options.stdin == "open")
    table.insert(workers, {line = line, exit = exit}); return #workers
end
local function validate(_, result)
    if result.invalid then return nil, "invalid capture" end
    return result
end
local search = (function()
__MODULE__
end)()(spawn, validate)
local function ask(query)
    search({query = query}, function(value, error) results[query] = {value = value, error = error} end)
end
local function reply(worker, request, result)
    workers[worker].line(json.encode({id = written[request].value.id, ok = true, result = result or {items = {}}}))
end
ask("first")
for i = 1, 100 do ask("q" .. i) end
assert(#workers == 1 and #written == 1)
assert(results.q99.error == "Search superseded" and results.q100 == nil)
reply(1, 1)
assert(#written == 2 and written[2].value.params.query == "q100")
reply(1, 1, {items = {"late"}})
assert(results.q100 == nil)
reply(1, 2)
assert(results.q100.value and #workers == 1)
local idle = timers[#timers]
assert(idle.ms == 120000 and not idle.cancelled)
ask("warm"); assert(idle.cancelled and #workers == 1)
reply(1, 3, {items = {}, invalid = true}); assert(results.warm.error == "invalid capture")
timers[#timers].f(); assert(killed[1] == 1)
ask("new"); assert(#workers == 2)
workers[1].exit(); assert(results.new == nil)
ask("after timeout")
local timeout = timers[#timers]; assert(timeout.ms == 60000); timeout.f()
assert(results.new.error:find("timed out", 1, true) and killed[2] == 2 and #workers == 3)
workers[2].exit(); assert(results["after timeout"] == nil)
reply(3, 5); assert(results["after timeout"].value)
workers[3].exit()
ask("after exit"); assert(#workers == 4)
workers[4].exit(); assert(results["after exit"].error:find("stopped", 1, true))
print("PASS: persistent search keeps one worker, one request and one latest query; rejects stale replies, validates data, expires idle models and replaces timed-out workers safely")
'''.replace('__MODULE__', source)
run_checks(args, checks, 'PASS: persistent search', 'deriva search')
