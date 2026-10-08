"""Exercise the Windows desktop bridge with explicit native success/failure replies."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
source = Path(__file__).with_name('desktop-agent.luau').read_text(encoding='utf-8')
checks = r'''
local install = (function()
__SOURCE__
end)()
local jobs, replies = {}, {}
local native = {}
local cancelled = 0
native.call = function(name) assert(name=='desktop.cancel');cancelled+=1 end
native.ask_async = function(name,args,done) jobs[#jobs+1]={name=name,args=args,done=done,query=true} end
native.call_async = function(name,args,done) jobs[#jobs+1]={name=name,args=args,done=done} end
local dispatch = install(native)
local function reply(ok,text,extra) replies[#replies+1]={ok=ok,text=text,extra=extra} end
assert(not dispatch('open_app',{},reply))
assert(dispatch('desktop_windows',{},reply))
jobs[#jobs].done({epoch=42,windows={{id='27',program='fixture',title='Español 日本語',monitor='display2',box={x=-1920,y=0,width=420,height=320},dialogof='',focused=false}},monitors={{id=1,name='display2',primary=false,box={x=-1920,y=0,width=1920,height=1080}}}})
assert(replies[#replies].ok and replies[#replies].text:find('27 fixture «Español 日本語»',1,true))
assert(replies[#replies].text:find('shared foreground',1,true))
dispatch('desktop_look',{pid='27'},reply)
jobs[#jobs].done({data='owned png',width=420,height=320})
assert(replies[#replies].extra.image.data=='owned png')
dispatch('desktop_click',{pid='27',x=20,y=40},reply)
assert(jobs[#jobs].name=='desktop.click' and jobs[#jobs].args[1]==42 and jobs[#jobs].args[5]=='left' and jobs[#jobs].args[6]==1)
jobs[#jobs].done('point is covered',-1)
assert(replies[#replies].ok==false and replies[#replies].text=='point is covered')
dispatch('desktop_type',{pid='27',text='Hola ñ 🚀'},reply)
assert(jobs[#jobs].args[3]=='Hola ñ 🚀')
jobs[#jobs].done('',0)
assert(replies[#replies].ok==true)
dispatch('desktop_type_secret',{pid='27',name='Saved name'},reply)
assert(jobs[#jobs].name=='desktop.type_secret' and #jobs[#jobs].args==3 and jobs[#jobs].args[3]=='Saved name')
jobs[#jobs].done('credential unavailable',1)
assert(not replies[#replies].ok)
dispatch('desktop_look',{pid='27'},reply)
local old=jobs[#jobs]
local count=#replies
dispatch('cancel',{},reply)
assert(jobs[#jobs].name=='desktop.done')
assert(cancelled==1)
old.done({data='late',width=1,height=1})
assert(#replies==count)
dispatch('desktop_type',{pid='27',text='old catalog'},reply)
assert(not replies[#replies].ok and replies[#replies].text:find('List windows',1,true))
native.ask_async=function() error('permission denied') end
dispatch('desktop_windows',{},reply)
assert(not replies[#replies].ok and replies[#replies].text:find('permission denied',1,true))
log('PASS: native desktop bridge, Unicode, image transport, failures and stale callbacks')
'''.replace('__SOURCE__', source)
run_checks(args, checks, 'PASS: native desktop bridge', 'desktop-agent')
