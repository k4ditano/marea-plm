"""Vault callbacks, pagination and deletion identities without real credentials."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks
p=argparse.ArgumentParser(description=__doc__);runner_arguments(p);args=p.parse_args()
source=Path(__file__).with_name('chat-credentials.luau').read_text(encoding='utf-8')
checks=r'''
local fact,text,model,handlers,jobs={},{},{},{},{}
local secrets,secret_named
local function tr(s) return s end
local function first_letters(s,n) local i=utf8.offset(s,n+1);return i and s:sub(1,i-1) or s end
local function emit() end
local function on(name,callback) handlers[name]=callback end
local native_sys={}
native_sys.ask_async=function(name,args,done) jobs[#jobs+1]={name=name,args=args,done=done} end
native_sys.call_async=native_sys.ask_async
__SOURCE__
assert(jobs[1].name=='credentials.list' and not fact['keys.readable'])
local names={} for i=1,30 do names[i]='Saved name '..i end
jobs[1].done(names,nil)
assert(#secrets==30 and fact['keys.pages']==3 and #model['keys.rows']==12)
local stale=model['keys.rows'][1].token
handlers.keys_page(1);handlers.keys_page(1)
assert(fact['keys.page']==3 and #model['keys.rows']==6)
local count=#jobs
handlers.keys_drop(stale);assert(#jobs==count,'stale row deleted another credential')
handlers.keys_drop(model['keys.rows'][1].token)
assert(jobs[#jobs].args[1]=='Saved name 25')
jobs[#jobs].done('denied',1)
assert(#secrets==30 and text['keys.status']:find('could not',1,true))
text['keys.name']='New name';text['keys.value']='dummy password, not a real secret'
handlers.keys_keep();handlers.keys_keep()
assert(#jobs==count+2 and jobs[#jobs].name=='credentials.set')
jobs[#jobs].done('denied',1)
assert(text['keys.value']=='dummy password, not a real secret' and #secrets==30)
handlers.keys_keep();jobs[#jobs].done('',0)
assert(text['keys.value']=='' and jobs[#jobs].name=='credentials.list')
jobs[#jobs].done(nil,'list failed')
assert(not fact['keys.readable'] and text['keys.status']:find('could not',1,true))
handlers['fact:section']('keys');jobs[#jobs].done({'New name'},nil)
assert(fact['keys.readable'] and fact['keys.page']==1 and #secrets==1 and text['keys.status']=='')
handlers.keys_drop(model['keys.rows'][1].token);jobs[#jobs].done('',0);jobs[#jobs].done({},nil)
assert(#secrets==0 and fact['keys.count']==0)
native_sys.call_async=function() error('queue full') end
text['keys.name']='Another';text['keys.value']='dummy'
handlers.keys_keep();assert(text['keys.value']=='dummy')
assert(text['keys.status']:find('could not',1,true))
log('PASS: native credential names, failed writes/deletes/lists, pagination and stale rows; no real vault accessed')
'''.replace('__SOURCE__',source)
run_checks(args,checks,'PASS: native credential','chat-credentials')
