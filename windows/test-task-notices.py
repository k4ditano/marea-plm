"""Task-notice callbacks consume native selections once; no notification or input is sent."""
from pathlib import Path
import argparse
from logic_test import runner_arguments,run_checks
p=argparse.ArgumentParser(description=__doc__);runner_arguments(p);args=p.parse_args()
module=Path(__file__).with_name('task-notices.luau').read_text(encoding='utf-8')
checks=r'''
local sent, asks, timers, chosen, text = {}, {}, {}, {}, {}
local now = 100000
local os = {time = function() return now end}
local function tr(s) return s end
local function after(ms, fn) assert(ms == 500);timers[#timers+1] = fn end
local native_sys = {
    call_async = function(name, args, done) sent[#sent+1] = {name=name,args=args,done=done} end,
    ask_async = function(name, args, done) assert(name=='notifications.actions' and #args==0);asks[#asks+1]=done end,
}
__MODULE__
local function choose(v) chosen[#chosen+1]=v end
local function tick(events,code)
    assert(#timers==1);table.remove(timers,1)();assert(#asks==1);table.remove(asks,1)(events,code or 0)
end
notice('Task','Now?',{{'now','Hacerlo ahora'},{'skip','Dejarla'}},choose)
local tag=sent[1].args[3]
assert(sent[1].name=='notifications.publish' and #sent[1].args==4 and #timers==0)
sent[1].done(nil,0);assert(#timers==1)
tick({{tag='someone-else',action='now'},{tag=tag,action='arbitrary'}})
assert(#chosen==0)
tick({{tag=tag,action='now'},{tag=tag,action='now'},{tag=tag,action='skip'}})
assert(#chosen==1 and chosen[1]=='now' and #timers==0)
notice('Done','Look',{{'open','Verla'}},choose);local second=sent[#sent];second.done(nil,0)
tick({{tag=second.args[3],action='default'}});assert(chosen[2]=='default')
notice('Failure','No native broker',{{'now','Now'}},choose);sent[#sent].done(nil,-1)
assert(#timers==0 and text['tasks.status']~='')
notice('Expired','Too late',{{'now','Now'}},choose);local expired=sent[#sent];expired.done(nil,0)
now+=21601;tick({{tag=expired.args[3],action='now'}})
assert(#chosen==2 and #timers==0 and sent[#sent].name=='notifications.cancel')
notice('Retry','Read temporarily failed',{{'skip','Skip'}},choose);local retry=sent[#sent];retry.done(nil,0)
tick(nil,-1);assert(#chosen==2 and #timers==1)
tick({{tag=retry.args[3],action='skip'}});assert(chosen[3]=='skip' and #timers==0)
notice('Dismissed','Removed in Windows',{{'now','Now'}},choose);local dismissed=sent[#sent];dismissed.done(nil,0)
tick({{tag=dismissed.args[3],action='dismissed'}});assert(#chosen==3 and #timers==0)
for i=1,64 do notice('Task','Wait',{{'now','Now'}},choose);sent[#sent].done(nil,0) end
assert(#timers==1);local count=#sent
notice('Overflow','Wait',{{'now','Now'}},choose);assert(#sent==count)
now+=21601;tick({});assert(#timers==0)
notice('Info','No callback');assert(#sent[#sent].args==3);sent[#sent].done(nil,0);assert(#timers==0)
native_sys.call_async=function() error('native service unavailable') end
notice('Error','Throw',{{'now','Now'}},choose);assert(#timers==0)
print('TASK_NOTICES_PASS: own one-use actions, default activation, failures, expiry, retries, bounded callbacks and idle polling')
'''.replace('__MODULE__',module)
run_checks(args,checks,'TASK_NOTICES_PASS','task-notices')
