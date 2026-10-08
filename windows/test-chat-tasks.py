"""Shared task scheduling/storage with a deterministic clock and no model/desktop."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks, shared_logic
p=argparse.ArgumentParser(description=__doc__);runner_arguments(p);args=p.parse_args()
source=shared_logic()
start=source.index('    -- ── her tasks:');end=source.index('    -- ── what the panel asks',start)
module=source[start:end]
prefix=r'''
local hooks={language={}}
local fact,text,model,handlers,replies,jobs,timers={['chat.state']='idle',['chat.signed_in']=true},{},{},{},{},{},{}
local task_do,task_days,turn_over,running_task
local history,rows,asks,live,shown_row,shown,worker,ready={},{ {kind=1,text='Current chat'} },{},nil,nil,0,nil,false
local archive_ok,write_ok,start_ok=true,true,true
local archives,stored,starts=0,nil,0
local function copy(v) if type(v)~='table' then return v end local out={} for k,x in pairs(v) do out[k]=copy(x) end return out end
local os=table.clone(os)
local real_date,real_time=os.date,os.time
local instant=real_time({year=2026,month=10,day=5,hour=9,min=0,sec=0})
os.date=function(fmt,at) return real_date('!'..fmt,at or instant) end
os.time=function(at) return at and real_time(at) or instant end
local function tr(s) return s end
local function on(name,fn) handlers[name]=fn end
local function every(_,fn) timers[#timers+1]=fn end
local function after(_,fn) jobs[#jobs+1]={callback=fn} end
local function emit() end
local function log() end
local function first_letters(s,n) local at=utf8.offset(s,n+1);return at and s:sub(1,at-1) or s end
local function finish_row() end
local function answer(id,ok,text) replies[id]={ok=ok,text=text} end
local function add(kind,text) rows[#rows+1]={kind=kind,text=text};return #rows end
local function run(command,args,done) jobs[#jobs+1]={command=command,args=args,done=done} end
local function keep_talk() archives+=1;return archive_ok end
local function stop_idle() end
local function start_worker() starts+=1;if start_ok then worker=1;ready=true end end
local sent={}
local function send(value) sent[#sent+1]=value end
local function status(value) text['chat.status']=value end
local sys={ask=function() return copy(stored) end,call=function(name,file,value)
    assert(name=='files.write' and file=='tasks.json')
    if not write_ok then error('owned write failure') end
    stored=copy(value)
end}
__INIT__
__MODULE__
'''
checks=r'''
task_do('invalid','task_schedule',{what='Test',time='10:00',days=',,,'});assert(not replies.invalid.ok)
task_do('invalid','task_schedule',{what='Test',time='10:00',days='Monday,bogus'});assert(not replies.invalid.ok)
task_do('invalid','task_schedule',{what='Test',time='10:00',days='once:2026-02-31'});assert(not replies.invalid.ok)
task_do('invalid','task_schedule',{what='Test',time='29:00',days='daily'});assert(not replies.invalid.ok)
write_ok=false
task_do('failed','task_schedule',{what='Test',time='10:00',days='daily'})
assert(not replies.failed.ok and stored==nil and #model['tasks.rows']==0)
write_ok=true
for i=1,25 do task_do('add','task_schedule',{what='Task '..i,time='10:00',days='lunes,miércoles'});assert(replies.add.ok) end
assert(#stored.tasks==25 and stored.tasks[1].id=='t1' and fact['tasks.pages']==3)
assert(task_days('lunes,miércoles')=='Mon, Wed')
local stale=model['tasks.rows'][1].token
handlers.task_page(1);handlers.task_page(1)
assert(fact['tasks.page']==3 and #model['tasks.rows']==1 and model['tasks.rows'][1].what=='Task 25')
handlers.task_drop(stale);assert(#stored.tasks==25)
write_ok=false
handlers.task_flip(model['tasks.rows'][1].token);assert(stored.tasks[25].on and model['tasks.rows'][1].on==1)
task_do('remove','task_cancel',{id='t25'});assert(not replies.remove.ok and #stored.tasks==25)
write_ok=true
archive_ok=false
handlers.task_now(model['tasks.rows'][1].token)
assert(starts==0 and not running_task and rows[1].text=='Current chat' and stored.tasks[25].last==nil,
    tostring(starts)..' / '..tostring(running_task)..' / '..rows[1].text..' / '..tostring(stored.tasks[25].last and stored.tasks[25].last.day))
archive_ok=true;write_ok=false
handlers.task_now(model['tasks.rows'][1].token)
assert(starts==0 and not running_task and rows[1].text=='Current chat')
write_ok=true
handlers.task_now(model['tasks.rows'][1].token)
assert(starts==1 and running_task=='t25' and sent[#sent].text=='[Task] Task 25')
assert(sent[#sent].now:find('2026-10-05 09:00',1,true))
handlers.task_now(model['tasks.rows'][1].token);assert(#waiting_tasks==0)
fact['chat.state']='idle';turn_over({ok=true,said='Owned result'})
assert(not running_task and stored.tasks[25].last.ok)
task_do('remove','task_cancel',{id='t25'});assert(replies.remove.ok and fact['tasks.page']==2 and #stored.tasks==24)
-- A task queued behind the current turn must be resolved again when its timer fires.
fact['chat.state']='thinking'
handlers.task_now(model['tasks.rows'][1].token)
fact['chat.state']='idle';turn_over({ok=true,said='Chat ended'})
local delayed=jobs[#jobs].callback
assert(delayed)
local queued_id=task_shelf[model['tasks.rows'][1].token]
task_do('queued-remove','task_cancel',{id=queued_id})
local before=starts;delayed();assert(starts==before,'a deleted queued task ran')
-- No worker means failure, never a stuck running task or queued phantom prompt.
worker=nil;ready=false;start_ok=false
handlers.task_now(model['tasks.rows'][1].token)
assert(not running_task and fact['chat.state']~='thinking')
for i=#stored.tasks+1,120 do task_do('add','task_schedule',{what='Task '..i,time='10:00',days='daily'});assert(replies.add.ok) end
task_do('full','task_schedule',{what='One too many',time='10:00',days='daily'})
assert(not replies.full.ok and #stored.tasks==120 and fact['tasks.pages']==10)
print('PASS: shared scheduled tasks durable errors, archive retention, weekday/date validation, bounded paging and worker failure')
'''
run_checks(args,prefix.replace('__INIT__','').replace('__MODULE__',module)+checks,'PASS: shared scheduled','chat-tasks')
for label,init in [('sequence',"stored={tasks={},next='invalid'}"),('schema',"stored={tasks={'invalid'},next=2}"),('unreadable',"sys.ask=function() error('owned read failure') end")]:
    check="""
task_do('failed','task_schedule',{what='Do not overwrite',time='10:00',days='daily'})
assert(not replies.failed.ok and not fact['tasks.readable'] and starts==0)
print('PASS: invalid task storage stays untouched')
"""
    run_checks(args,prefix.replace('__INIT__',init).replace('__MODULE__',module)+check,'PASS: invalid task','chat-tasks-'+label)

run_checks(args,prefix.replace('__INIT__', 'stored={tasks={},next=80}').replace('__MODULE__',module)+'\ntask_do("resume","task_schedule",{what="Next id",time="10:00",days="daily"});assert(replies.resume.ok and stored.tasks[1].id=="t80");print("PASS: persisted task sequence")','PASS: persisted task sequence','chat-task-sequence')
