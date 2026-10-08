"""Test native helper dispatch/error recovery independently of Node and desktop APIs."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks
parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('agent-reader.luau').read_text(encoding='utf-8')
generated = Path(__file__).resolve().parents[1].joinpath('marea-desktop.luau').read_text(encoding='utf-8')
presentation = generated.split("-- ── the agents' reservoirs", 1)[1].split('-- ── glances', 1)[0]
presentation = presentation[presentation.index('local agents = {}'):]
checks = r'''
local fact, text, handlers, notices, requests = {}, {}, {}, {}, {}
local function on(name, callback) handlers[name] = callback end
local function notice(message) notices[#notices + 1] = message end
local install = (function()
__MODULE__
end)()
local reject = false
local read = install(function(command, args, done, options)
    if reject then error("permission denied") end
    assert(command == "node" and args[1] == "tools/reservas" and args[2] == "--lines")
    assert(options.cwd == ".")
    requests[#requests + 1] = done
end, notice)
local received
read(function(output, code) received = {output, code} end)
requests[1]("missing node", -1)
assert(received[2] == -1 and #notices == 0)
assert(text.windows_agents_status:find("Node.js"))
fact.page = "agents"; handlers["fact:page"]("agents")
assert(#notices == 1)
read(function(output, code) received = {output, code} end)
requests[2]("now\t123\n", 0)
assert(received[2] == 0 and text.windows_agents_status:find("Todavia"))
handlers["fact:page"]("agents"); assert(#notices == 1, "stale errors must clear")
reject = true
read(function(output, code) received = {output, code} end)
assert(received[2] == -1 and #notices == 2, "synchronous failure must release the reader")
log("PASS: agent helper arguments, scene-relative directory, missing runtime and retry recovery")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: agent helper arguments', 'agent-reader')
presentation_checks = r'''
local fact, text, handlers, timers = {}, {}, {}, {}
local now, emitted, callback = 20000, 0, nil
local os = {time = function() return now end}
local function tr(s) return s end
local function on(name, cb) handlers[name] = cb end
local function after(_, cb) timers.initial = cb end
local function every(delay, cb) timers[delay] = cb end
local function emit(name) assert(name == "agents_read"); emitted += 1 end
local function run(_, _, cb) callback = cb end
__PRESENTATION__
local function read(observed, used, reset)
    handlers.agents_refresh()
    callback("agent\tclaude\tClaude Code\t\t\t\nagent\tcodex\tCodex\tPro\tlocal\t" .. observed ..
        "\nlimit\tcodex\tWeekly\t10080\t" .. used .. "\t" .. reset .. "\t1\t0\n", 0)
end
read(now - 10, "27", now + 50)
assert(text["ag.sub.1"] == "Sin datos de cuota")
assert(text["ag.sub.2"]:find("on this machine") and fact["ag.worst"] == 73)
assert(fact["ag.used.2.1"] == 27 and not fact["ag.pending.2.1"])
read(now - 1000, "27", now + 50)
assert(fact["ag.worst"] == 101 and fact["ag.used.2.1"] == 27, "stale observations stay visible but cannot drive the face")
read(now + 60, "27", now + 100)
assert(fact["ag.worst"] == 101 and not text["ag.sub.2"]:find("just now"))
read(now, "", now + 100)
assert(fact["ag.used.2.1"] == -1 and fact["ag.worst"] == 101)
read(now, "100", now - 1)
assert(fact["ag.pending.2.1"] and fact["ag.used.2.1"] == 100 and fact["ag.worst"] == 101)
read(now, "0", now + 50)
assert(fact["ag.worst"] == 100, "a real zero differs from an unknown value")
now += 60; timers[30000]()
assert(fact["ag.pending.2.1"] and fact["ag.worst"] == 101)
handlers.agents_refresh(); callback("failure", 1)
handlers.agents_refresh(); callback("now\t" .. now .. "\n", 0)
assert(fact["ag.kind.1"] == 0 and fact["ag.kind.2"] == 0 and fact["ag.worst"] == 101)
log("PASS: quota presentation, real zero, missing data, stale/future observations, expiry and retry")
'''.replace('__PRESENTATION__', presentation)
run_checks(args, presentation_checks, 'PASS: quota presentation', 'agent-presentation')
