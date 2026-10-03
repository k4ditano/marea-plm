"""Test native weather transport without sending network requests."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('weather.luau').read_text(encoding='utf-8')
checks = r'''
local install = (function() __MODULE__ end)()
local requests, notices, results = {}, {}, {}
local fetch = install(function(command, args, done, options)
    assert(command == "curl.exe" and options.cwd == "C:\\Windows\\System32")
    requests[#requests + 1] = {args=args, done=done}
end, {ask=function(_, name) assert(name == "SystemRoot"); return "C:\\Windows" end},
function(message) notices[#notices + 1] = message end)
local function done(out, code) results[#results + 1] = {out, code} end
local url = "https://geocoding-api.open-meteo.com/v1/search?name=Le%C3%B3n&count=1"
fetch({"-s", "--max-time", "10", url}, done)
assert(#results == 0 and #requests == 1)
assert(requests[1].args[6] == url and requests[1].args[3] == "--fail")
requests[1].done('{"results":[]}', 0)
assert(results[1][1] == '{"results":[]}' and results[1][2] == 0)
fetch({"-s", "--max-time", "10", "https://api.open-meteo.com/v1/forecast?latitude=40"}, done)
requests[2].done("timeout", 28)
assert(results[2][1] == "" and results[2][2] == 28 and #notices == 1)
for _, bad in ipairs({"file:///C:/secret", "https://api.open-meteo.com.evil.test/v1/forecast?", "https://example.com"}) do
    fetch({"-s", "--max-time", "10", bad}, done)
end
assert(#requests == 2 and #results == 5 and results[5][2] == -1)
log("PASS: native weather transport, Unicode URL, asynchronous completion and failures")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: native weather transport', 'weather')
