"""Window selection closes the overview only after native focus acknowledgement."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = (Path(__file__).resolve().parents[1] / 'tools/windows-overview.luau').read_text(encoding='utf-8')
checks = r'''
local handlers, timers, requests = {}, {}, {}
local fact, text = {["win.0.open"]=true,["win.1.open"]=true,["win.focus"]=-1}, {}
local sys = {ask=function(service,key) assert(service=="env" and key=="MAREA_LOCALE");return "es" end}
local function tr(s) return s end
local function on(name,callback) handlers[name]=callback end
local function after(ms,callback) assert(ms==1000);timers[#timers+1]=callback end
local function run(command,args,callback)
    assert(command=="pleamar-wm" and args[1]=="--say" and args[2]=="windows-overview" and args[3]=="quit")
    requests[#requests+1]=callback
end
__MODULE__
assert(fact.locale=="es")
for _,slot in ipairs({-1,32,0.5,"0",2}) do handlers.overview_select(slot) end
assert(#timers==0 and #requests==0)
handlers.overview_select(0);handlers.overview_select(0)
timers[1]();assert(text.overview_status=="" and #requests==0)
timers[2]();assert(text.overview_status:find("did not activate",1,true) and #requests==0)
fact["win.focus"]=0;handlers["fact:win.focus"](0)
assert(#requests==0) -- An expired selection cannot dismiss a later view.
handlers.overview_select(1)
fact["win.focus"]=1;handlers["fact:win.focus"](1)
assert(#requests==1)
handlers.overview_close();assert(#requests==1)
requests[1]("unavailable",1);assert(text.overview_status:find("could not close",1,true))
handlers.overview_close();assert(#requests==2)
requests[2]("",0);timers[3]();assert(#requests==2)
log("PASS: overview selection validates slots, native focus acknowledgements, stale timers and close failures")
'''
run_checks(args, checks.replace('__MODULE__', module), 'PASS: overview selection', 'window-overview')
