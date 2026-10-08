"""Exercise the software page with deterministic WinGet responses; no installs."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('software.luau').read_text(encoding='utf-8')
checks = r'''
local fact, text, model, handlers, jobs, timers, notices, runs = {['sw.state']='idle'}, {}, {}, {}, {}, {}, {}, {}
local hooks = {}
local json = {encode=function(v) return v end, decode=function(v) assert(type(v)=='table'); return v end}
local function tr(s) return s end
local function on(n, f) handlers[n] = f end
local function after(_, f) timers[#timers+1] = f end
local function every(_, _) end
local function log(...) end
local function notice(s) notices[#notices+1] = s end
local function spawn(name, args, line, done, options)
    assert(name=='powershell.exe' and args[7]=='tools/software.ps1')
    assert(options.cwd=='.' and options.errors==true)
    jobs[#jobs+1] = {payload=options.input, line=line, done=done}
    return #jobs
end
local function run(name, args, done, options) runs[#runs+1] = options.input; done('',0) end
local function answer(index, value)
    value.type = 'result'; jobs[index].line(value); jobs[index].done('',0)
end
local function tick() local due=timers; timers={}; for _, f in ipairs(due) do f() end end
local install = (function() __MODULE__ end)()
install(run, spawn, hooks, notice)
timers = {} -- Background scans have their own clock, separate from the debounce below.
handlers.sw_open(); handlers.sw_check(); assert(#jobs==1 and fact['sw.state']=='scanning')
answer(1,{ok=true,items={{id='A.App',name='App A',old='1',version='2'},{id='B.App',name='App B',old='3',version='4'}}})
assert(fact['sw.count']==2 and fact['sw.ticked']==2 and model['sw.rows'][1].versions=='1 → 2')
handlers.sw_toggle(0); assert(fact['sw.ticked']==1)
handlers.sw_go(); handlers.sw_go(); assert(#jobs==1 and fact['sw.state']=='unlocking')
handlers.sw_forget(); assert(#jobs==1 and fact['sw.state']=='ready')
handlers.sw_go(); handlers.sw_auth(); handlers.sw_auth()
assert(#jobs==2 and jobs[2].payload.action=='update')
assert(#jobs[2].payload.packages==1 and jobs[2].payload.packages[1].id=='B.App')
assert(jobs[2].payload.packages[1].version=='4' and fact['sw.state']=='working')
jobs[2].line({type='started',token='owned-token'})
jobs[2].line({type='progress',percent=-1,stage='Installing',item='App B'})
assert(fact.windows_sw_indeterminate and text['sw.item']=='App B')
jobs[2].line({type='progress',percent=32,stage='Installing',item='App B'})
assert(not fact.windows_sw_indeterminate and fact['sw.progress']==.32)
handlers.sw_stop(); handlers.sw_stop()
assert(#runs==1 and runs[1].action=='cancel' and runs[1].token=='owned-token')
answer(2,{ok=false,cancelled=true,error='cancel requested',completed={'B.App'}})
assert(fact['sw.state']=='failed' and fact['sw.count']==1 and text['sw.error']=='cancel requested')
handlers.sw_back(); answer(3,{ok=false,error='offline'})
assert(fact['sw.state']=='broken' and fact['sw.count']==1, 'failure reported up to date')
handlers.sw_check(); answer(4,{ok=true,items={}})
assert(fact['sw.state']=='ready' and fact['sw.count']==0)
-- Catalogue identity, stale reply, single in-flight query and installed guard.
text['sw.query']='old'; handlers['text:sw.query'](); tick()
assert(jobs[5].payload.query=='old')
text['sw.query']='new'; handlers['text:sw.query'](); tick(); assert(#jobs==5)
answer(5,{ok=true,items={{id='Old.App',name='Old',version='1'}}})
assert(#model['sw.found']==0 and #jobs==6 and jobs[6].payload.query=='new')
answer(6,{ok=true,items={{id='New.Id',name='Friendly app name',version='5',installed=false},{id='Present.Id',name='Present',version='1',installed=true}}})
handlers.sw_install(1); assert(fact['sw.state']=='ready')
handlers.sw_install(0); assert(#jobs==6 and fact['sw.state']=='unlocking')
handlers.sw_auth(); assert(jobs[7].payload.action=='install' and jobs[7].payload.packages[1].id=='New.Id')
answer(7,{ok=true,completed={'New.Id'},reboot=true})
assert(fact['sw.state']=='finished' and fact['sw.reboot'] and text['sw.result']=='Friendly app name is installed')
local rows
hooks.packages('query', function(v) rows=v end)
answer(8,{ok=true,items={{id='Found.Id',name='Found',version='1'},{id='Installed.Id',name='Already',version='2',installed=true}}})
assert(#rows==1 and rows[1].package=='Found.Id')
text['sw.query']='offline'; handlers['text:sw.query'](); tick()
answer(9,{ok=false,error='network unavailable'})
assert(text.windows_sw_search_error:find('network unavailable') and #model['sw.found']==0)
-- A delayed scan may finish while the user installs a catalogue result.
handlers.sw_check(); assert(jobs[10].payload.action=='scan')
text['sw.query']='concurrent'; handlers['text:sw.query'](); tick()
answer(11,{ok=true,items={{id='Concurrent.App',name='Concurrent',version='1'}}})
handlers.sw_install(0); handlers.sw_auth(); assert(fact['sw.state']=='working')
answer(10,{ok=true,items={{id='Existing.App',name='Existing',old='1',version='2'}}})
assert(fact['sw.state']=='working', 'late scan hid the active install/cancel controls')
answer(12,{ok=true,completed={'Concurrent.App'}})
assert(fact['sw.state']=='finished')
log('PASS: software selection, explicit confirmation, exact IDs/versions, streamed progress, cancellation, partial failure, catalogue races and finder')
'''.replace('__MODULE__', module).replace('local function log(...) end', 'local log = log')
run_checks(args, checks, 'PASS: software selection', 'software')

# The native model returns copies. Appending delayed catalogue results must keep
# keyboard selection by row identity rather than by Lua table identity.
search = Path(__file__).with_name('search.luau').read_text(encoding='utf-8')
search_checks = r'''local fact, text, model = {selected=0}, {query="query"}, {}
local timers, file_reply, package_reply = {}, nil, nil
local generation, home_dir, OWN, open_windows = 0, ".", {}, {}
local apps = {{name="First",exec="first.exe"},{name="Second",exec="second.exe"}}
local search_match = {fold=function(v) return v end,score=function(_,_) return 1 end}
local hooks = {packages=function(_,done) package_reply=done end}
local sys = {ask_async=function(_,_,done) file_reply=done end}
local function tr(s) return s end
local function after(ms,fn) timers[ms]=fn end
local function prefer(a,b) return a.name < b.name end
local function paint(_,rows)
    model.results={}
    for _,row in ipairs(rows) do model.results[#model.results+1]=table.clone(row) end
    fact.selected=0
end
__SEARCH__
search()
fact.selected=1
timers[120](); file_reply({items={{name="File",path="C:/query.txt"}}},nil)
assert(fact.selected==1 and model.results[2].exec=="second.exe")
timers[400](); package_reply({{name="Package",package="Publisher.App"}})
assert(fact.selected==1 and #model.results==4, "catalogue append lost keyboard selection")
text.query="new query"; search()
package_reply({{name="Stale",package="Old.App"}})
assert(#model.results==2,"obsolete catalogue reply repainted new query")
log("PASS: asynchronous finder selection and stale catalogue replies")
'''.replace('__SEARCH__', search)
run_checks(args, search_checks, 'PASS: asynchronous finder selection', 'software-search')
