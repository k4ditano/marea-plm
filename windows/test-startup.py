"""Startup UI reads actual state, deduplicates and reports OS disables/errors."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks
parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('startup.luau').read_text(encoding='utf-8')
checks = r'''
local fact, text, handlers, requests, timers, notices = {}, {}, {}, {}, {}, {}
local json = {encode=function(value) return value end, decode=function(value) assert(type(value) == "table"); return value end}
local function tr(s) return s end
local function on(n, fn) handlers[n] = fn end
local function after(_, fn) timers[#timers+1] = fn end
local function run(name, args, done)
    assert(name == "powershell.exe" and args[7] == "tools/startup.ps1")
    requests[#requests+1] = {action=args[9], done=done}
end
local install = (function() __MODULE__ end)()
install(run, {}, function(s) notices[#notices+1] = s end)
assert(#requests == 1 and requests[1].action == "state" and fact.windows_startup_busy)
handlers.windows_toggle_startup(); assert(#requests == 1)
requests[1].done(json.encode({available=true, enabled=false, registered=false}), 0)
handlers.windows_toggle_startup(); handlers.windows_toggle_startup()
assert(#requests == 2 and requests[2].action == "enable")
requests[2].done(json.encode({available=true, enabled=true, registered=true}), 0)
assert(fact.windows_startup_enabled and not fact.windows_startup_busy)
handlers.windows_toggle_startup(); assert(requests[3].action == "disable")
requests[3].done(json.encode({available=true, enabled=false, registered=false}), 0)
handlers["fact:page"]("settings"); requests[4].done(json.encode({available=true, enabled=false, registered=true, blocked=true}),0)
assert(not fact.windows_startup_enabled and text.windows_startup_status == "Disabled in Windows startup apps")
handlers.windows_toggle_startup(); assert(requests[5].action == "disable")
requests[5].done("invalid json", 1)
assert(not fact.windows_startup_available and #notices == 1)
handlers["fact:page"]("settings"); timers[#timers]()
assert(not fact.windows_startup_busy and #notices == 2)
requests[6].done(json.encode({available=true, enabled=true}), 0)
assert(not fact.windows_startup_enabled, "late success replaced timeout state")
handlers["fact:page"]("settings"); requests[7].done(json.encode({available=false,reason="installed-only"}),0)
assert(text.windows_startup_status == "Available after installation")
log("PASS: startup readback, opt-in/out, busy guards, Windows disable, error and timeout")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: startup readback', 'startup')
