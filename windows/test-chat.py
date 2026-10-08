"""Check the actual shared chat's login lifecycle without accounts or a desktop."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks, shared_logic

parser=argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args=parser.parse_args()
source=shared_logic()
start=source.index('local function chat()\n')
end=source.index('\nchat()',start)+len('\nchat()')
chat=source[start:end]
checks=r'''
local fact, text, model = {['chat.state']='idle',locale='es'}, {}, {}
local handlers, jobs, writes, runs, wire, timers, kills = {}, {}, {}, {}, {}, {}, {}
local settings, apps, hooks = {}, {{name='Fixture App',exec='fixture:app',id='fixture'}}, {language={}}
local home_dir = 'C:/owned test user'
local launches = {}
local browser_code, browser_pending, browser_hold = 0, nil, false
local chat_desktop = function() return false end
local open_reply, open_code, hold_open, pending_open = 'no agent socket here', 1, false, nil
local sys = {ask=function(name) if name=='env' then return 'C:/owned state' end if name=='files.list' then return {} end return nil end,call=function() end,
    call_async=function(name,args,done) assert(name=='apps.launch');launches[#launches+1]={args=args,done=done} end}
local function tr(value) return value end
local function save_settings() end
local function on(name, handler) handlers[name]=handler end
local function after(delay, callback)
    local timer={delay=delay}
    timer.run=function() timer.fired=true;callback() end
    timers[#timers+1]=timer;return #timers
end
local function cancel(id) timers[id].cancelled=true end
local function every() end
local function emit() end
local json = {}
json.encode=function(value) wire[#wire+1]=value;return '{'..#wire..'}' end
json.decode=function(value) local id=tonumber(value:match('^{(%d+)}%s*$'));assert(id and wire[id]);return wire[id] end
local function run(command,args,callback)
    runs[#runs+1]={command=command,args=args}
    if callback then
        if command=='xdg-open' then
            if browser_hold then browser_pending=callback else callback('',browser_code) end
        elseif args[1]=='agent' and args[2]=='open' then
            if hold_open then pending_open=callback else callback(open_reply,open_code) end
        else callback('',0) end
    end
end
local function spawn(command,args,line,exit,options) assert(options.stdin=='open');jobs[#jobs+1]={line=line,exit=exit};return #jobs end
local function write(id,line) writes[#writes+1]={id=id,message=json.decode(line)};return true end
local function kill(id) kills[#kills+1]=id end
__CHAT__
local function event(value) jobs[#jobs].line(json.encode(value)) end
local function count(kind)
    local n=0
    for _,entry in ipairs(writes) do if entry.message.type==kind then n+=1 end end
    return n
end
-- Cancel before the SDK becomes ready: never replay a queued sign-in later.
handlers.chat_login();assert(fact['chat.signing']==true and #jobs==1)
handlers.chat_login();assert(#jobs==1)
handlers.chat_login_cancel();assert(fact['chat.signing']==false)
event({type='ready',usable=false,reason='signed_out',models={}})
assert(count('login')==0,'cancelled login was sent when the worker became ready')
event({type='login_url',url='https://auth.openai.com/codex/device',code='ABCD-EFGH'})
assert(#runs==0,'late login opened a browser after cancellation')
-- A requested login shows the code and opens exactly the expected target.
handlers.chat_login();assert(count('login')==1)
event({type='login_url',url='https://auth.openai.com/codex/device',code='ABCD-EFGH'})
assert(#runs==1 and runs[1].command=='xdg-open')
assert(text['chat.login_hint']=='Enter this code in your browser: ABCD-EFGH')
assert(fact['chat.login_link'] and text['chat.login_help']:find('Security',1,true))
browser_code=1;handlers.chat_login_open()
assert(text['chat.status']:find('Could not open the browser',1,true))
assert(fact['chat.signing'] and text['chat.login_hint']:find('ABCD-EFGH',1,true))
browser_code=0;handlers.chat_login_open();assert(text['chat.status']=='')
browser_hold=true;handlers.chat_login_open();assert(browser_pending)
local login_runs=#runs

handlers.chat_login_cancel()
assert(text['chat.login_hint']=='' and fact['chat.signing']==false)
assert(fact['chat.login_link']==false and text['chat.login_help']=='')
handlers.chat_login_open();assert(#runs==login_runs)
text['chat.status']='new status';browser_pending('',1)
assert(text['chat.status']=='new status','late browser failure changed the cancelled login')
browser_hold=false
-- Untrusted worker output must never become an arbitrary shell launch.
handlers.chat_login()
event({type='login_url',url='file:///C:/Windows/notepad.exe'})
assert(#runs==login_runs and fact['chat.signing']==false)
assert(text['chat.status']=='The sign-in address was not recognized.')
-- Worker death clears sign-in state, its code and pending login messages.
handlers.chat_login()
jobs[1].exit('',1)
assert(fact['chat.signing']==false and text['chat.login_hint']=='')
handlers.chat_login();assert(#jobs==2)
handlers.chat_login_cancel()
local before=count('login')
event({type='ready',usable=false,reason='signed_out',models={}})
assert(count('login')==before)
-- Application launch success comes from the native callback, never pcall alone.
fact['chat.free']=true
local before_result=count('result')
event({type='propose',id='launch-denied',tool='open_app',args={name='Fixture App'}})
assert(#launches==1 and launches[1].args[1]=='fixture:app')
assert(count('result')==before_result)
launches[1].done('OS denied launch',-1)
assert(writes[#writes].message.ok==false and writes[#writes].message.text=='OS denied launch')
event({type='propose',id='launch-ok',tool='open_app',args={name='Fixture App'}})
launches[2].done('',0)
assert(writes[#writes].message.ok==true and writes[#writes].message.text:find('Launch requested',1,true))
-- A cancelled/new conversation must not receive late results from old work.
event({type='propose',id='launch-late',tool='open_app',args={name='Fixture App'}})
handlers.chat_stop()
before_result=count('result')
launches[3].done('',0)
assert(count('result')==before_result,'late launch result escaped cancellation')
-- Upstream Linux has sys.call but not the port's asynchronous extension.
chat_desktop=nil
local native_launch=sys.call_async
sys.call_async=nil
sys.call=function(name,value) assert(name=='apps.launch' and value=='fixture:app');error('Linux launch denied') end
event({type='propose',id='linux-denied',tool='open_app',args={name='Fixture App'}})
assert(writes[#writes].message.ok==false and writes[#writes].message.text:find('Linux launch denied',1,true))
sys.call=function(name,value) assert(name=='apps.launch' and value=='fixture:app') end
event({type='propose',id='linux-ok',tool='open_app',args={name='Fixture App'}})
assert(writes[#writes].message.ok==true and writes[#writes].message.text:find('Launch requested',1,true))
-- Linux keeps the upstream monitor-aware WM route; it must not double-launch
-- or fall through to the ordinary launcher after cancellation or a WM error.
local service_calls=0
sys.call=function() service_calls+=1 end
open_reply,open_code='opened on monitor 1 (process 123): fixture',0
event({type='propose',id='wm-ok',tool='open_app',args={name='Fixture App',monitor=1}})
assert(writes[#writes].message.ok and writes[#writes].message.text:find('on monitor 1',1,true))
assert(runs[#runs].args[3]=='--monitor' and runs[#runs].args[4]=='1' and service_calls==0)
open_reply,open_code='open: stopped-by-user',1
event({type='propose',id='wm-stopped',tool='open_app',args={name='Fixture App'}})
assert(not writes[#writes].message.ok and service_calls==0)
open_reply,open_code='unknown successful reply',0
event({type='propose',id='wm-unknown',tool='open_app',args={name='Fixture App'}})
assert(not writes[#writes].message.ok and service_calls==0)
open_reply,open_code='no agent socket here',1
event({type='propose',id='wm-monitor-unavailable',tool='open_app',args={name='Fixture App',monitor=1}})
assert(not writes[#writes].message.ok and service_calls==0)
hold_open=true
event({type='propose',id='wm-late',tool='open_app',args={name='Fixture App'}})
handlers.chat_stop();before_result=count('result')
pending_open('no agent socket here',1)
assert(count('result')==before_result and service_calls==0,'cancelled WM attempt launched a fallback')
hold_open=false
chat_desktop=function() return false end
sys.call_async=native_launch
sys.call=function() end
local before_launch=#launches
event({type='propose',id='windows-monitor-unavailable',tool='open_app',args={name='Fixture App',monitor=1}})
assert(not writes[#writes].message.ok and #launches==before_launch)
event({type='propose',id='launch-new',tool='open_app',args={name='Fixture App'}})
chat_desktop=nil
handlers.chat_new()
before_result=count('result')
launches[4].done('',0)
assert(count('result')==before_result,'old action replied into a new conversation')
-- A new conversation waits for its previous worker, preserving the next input.
local before_prompt=count('prompt')
assert(fact['chat.state']=='starting' and count('shutdown')==1)
text['chat.input']='A message for the next conversation'
handlers.chat_send()
handlers.chat_login()
handlers.chat_stop()
assert(text['chat.input']=='A message for the next conversation')
assert(count('prompt')==before_prompt and #jobs==2 and fact['chat.signing']==false)
event({type='ready',usable=true,models={}})
event({type='delta',text='Stale response'})
assert(fact['chat.state']=='starting','retiring worker changed the new conversation')
local graceful_timeout=timers[#timers]
assert(graceful_timeout.delay==2000)
jobs[2].exit('',0)
assert(fact['chat.state']=='idle' and text['chat.status']=='')
handlers.chat_send()
assert(#jobs==3 and text['chat.input']=='' and count('prompt')==before_prompt)
event({type='ready',usable=true,models={}})
assert(count('prompt')==before_prompt+1 and writes[#writes].id==3)
assert(writes[#writes].message.text=='A message for the next conversation')
graceful_timeout.run()
assert(#kills==0,'an expired close timer killed a newer worker')
-- An unresponsive owned helper cannot block new conversations indefinitely.
handlers.chat_new()
local forced_timeout=timers[#timers]
assert(forced_timeout.delay==2000)
forced_timeout.run()
assert(#kills==1 and kills[1]==3 and fact['chat.state']=='idle')
text['chat.input']='After the timeout'
handlers.chat_send()
assert(#jobs==4 and fact['chat.state']=='thinking')
jobs[3].line(json.encode({type='failed',reason='late failure'}))
jobs[3].exit('',1)
assert(fact['chat.state']=='thinking','late exit interrupted the current worker')
event({type='ready',usable=true,models={}})
assert(writes[#writes].id==4 and writes[#writes].message.text=='After the timeout')
-- A failed archive keeps this conversation and its worker alive.
local before_shutdown=count('shutdown')
sys.call=function(name) if name=='files.write' then error('injected archive write failure') end end
handlers.chat_new()
assert(count('shutdown')==before_shutdown and fact['chat.state']=='thinking')
assert(text['chat.status']=='Could not save this conversation. It is still open.')
sys.call=function() end
-- Idle retirement uses the same bounded shutdown and retains conversation history.
event({type='done'})
local idle_timeout=timers[#timers]
assert(idle_timeout.delay==180000)
idle_timeout.run()
assert(fact['chat.state']=='starting' and writes[#writes].message.type=='shutdown')
jobs[4].exit('',0)
text['chat.input']='Continue our conversation'
handlers.chat_send()
assert(#jobs==5 and writes[#writes].message.type=='start')
assert(writes[#writes].message.history[1].text=='After the timeout')
-- A startup crash must not replay an unsent prompt into a new conversation.
jobs[5].exit('',1)
handlers.chat_new()
text['chat.input']='Only this new request'
handlers.chat_send()
assert(#jobs==6)
before_prompt=count('prompt')
event({type='ready',usable=true,models={}})
assert(count('prompt')==before_prompt+1,'a dead worker retained an old queued prompt')
assert(writes[#writes].id==6 and writes[#writes].message.text=='Only this new request')
-- Windows retires the SDK sooner only while both chat surfaces are hidden.
chat_desktop=function() return true end
local function change(name,value)
    fact[name]=value
    handlers['fact:'..name](value)
end
local function idle_timer()
    for i=#timers,1,-1 do
        local timer=timers[i]
        if not timer.cancelled and not timer.fired and (timer.delay==30000 or timer.delay==180000) then return timer end
    end
end
change('chatting',true)
event({type='done'})
assert(idle_timer().delay==180000)
change('chatting',false)
local hidden_timeout=idle_timer()
assert(hidden_timeout.delay==30000)
change('chatting',true)
assert(hidden_timeout.cancelled and idle_timer().delay==180000,'reopening did not extend the idle deadline')
change('open',true);change('page','settings');change('section','talk')
change('chatting',false)
assert(idle_timer().delay==180000,'visible account settings used the short deadline')
change('page','none')
assert(idle_timer().delay==30000)
change('page','settings')
assert(idle_timer().delay==180000)
change('open',false)
assert(idle_timer().delay==30000,'closed settings retained the SDK too long')
-- Long authentication must not lose the idle timer after completion/cancel.
handlers.chat_login();assert(idle_timer()==nil)
event({type='login_done',ok=false,reason='cancelled'})
assert(idle_timer().delay==30000)
handlers.chat_login();assert(idle_timer()==nil)
event({type='login_url',url='file:///invalid'})
assert(idle_timer().delay==30000)
handlers.chat_login();assert(idle_timer()==nil)
handlers.chat_login_cancel()
assert(idle_timer().delay==30000)
-- Thinking, approval and tool execution survive hidden panels without a deadline.
text['chat.input']='Keep working while closed'
handlers.chat_send()
change('chatting',false)
assert(idle_timer()==nil and fact['chat.state']=='thinking')
fact['chat.free']=false
event({type='propose',id='pending',tool='desktop_click',args={pid='1',x=20,y=30}})
change('chatting',false)
assert(idle_timer()==nil and fact['chat.state']=='awaiting')
fact['chat.free']=true
event({type='propose',id='active',tool='desktop_click',args={pid='1',x=20,y=30}})
change('open',false)
assert(idle_timer()==nil and fact['chat.state']=='acting')
event({type='done'})
assert(idle_timer().delay==30000)
idle_timer().run()
assert(writes[#writes].message.type=='shutdown')
jobs[6].exit('',0)
text['chat.input']='Resume the same thread'
handlers.chat_send()
assert(#jobs==7 and writes[#writes].message.type=='start')
assert(writes[#writes].message.history[1].text=='Only this new request')
-- A silent startup must not leave sign-in preparing forever or replay the queue.
handlers.chat_login()
assert(fact['chat.signing'])
local deadline
for _,timer in ipairs(timers) do
    if timer.delay==60000 and not timer.cancelled and not timer.fired then deadline=timer end
end
assert(deadline);deadline.run()
assert(fact['chat.state']=='offline' and not fact['chat.signing'])
assert(text['chat.status']=='Her engine did not respond. Try signing in again.')
assert(text['chat.login_hint']=='' and not fact['chat.login_link'])
local attempts=count('login')
jobs[7].line(json.encode({type='ready',usable=false,reason='signed_out',models={}}))
assert(count('login')==attempts,'timed-out worker replayed a login')
handlers.chat_login();assert(#jobs==8)
event({type='ready',usable=false,reason='signed_out',models={}})
assert(count('login')==attempts+1,'retry did not reach the new worker')
log('PASS: chat login, cancellation, worker retirement and truthful application launch')
'''.replace('__CHAT__',chat)
run_checks(args,checks,'PASS: chat login','chat')
