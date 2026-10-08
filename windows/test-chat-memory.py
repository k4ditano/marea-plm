"""Exercise shared memory logic with an isolated in-memory files service."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks, shared_logic

parser=argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args=parser.parse_args()
source=shared_logic()
start=source.index('    -- ── her memory ──')
end=source.index('    -- ── the worker ──',start)
checks=r'''
local hooks={language={}}
local store, handlers, timers, replies = {}, {}, {}, {}
local fact, text, model, rows = {}, {}, {}, {}
local fail_write, fail_remove, fail_list = nil, nil, false
local os = table.clone(os)
os.date = function() return '20261005-211000' end
local function emit() end
local function copy(value)
    if type(value)~='table' then return value end
    local out={} for k,v in pairs(value) do out[k]=copy(v) end return out
end
local sys={}
sys.ask=function(command,name)
    if command=='files.read' then return copy(store[name]) end
    assert(command=='files.list')
    if fail_list then error('injected directory error') end
    local names={} for name in pairs(store) do names[#names+1]=name end return names
end
sys.call=function(command,name,value)
    if command=='files.write' then
        if fail_write and (fail_write=='*' or fail_write==name) then error('injected write failure') end
        store[name]=copy(value)
    else
        assert(command=='files.remove')
        if fail_remove and (fail_remove=='*' or fail_remove==name) then error('injected deletion failure') end
        store[name]=nil
    end
end
local function tr(value) return value end
local function first_letters(s,n) local at=utf8.offset(s,n+1);return at and s:sub(1,at-1) or s end
local function add(kind,value,detail,state) rows[#rows+1]={kind=kind,text=value,detail=detail,state=state};return #rows end
local function finish_row(row,ok) rows[row].state=ok and 1 or 2 end
local function answer(id,ok,value) replies[id]={ok=ok,text=value} end
local function on(name,callback) handlers[name]=callback end
local function after(delay,callback) timers[#timers+1]={delay=delay,run=callback};return #timers end
local function cancel(id) timers[id].cancelled=true end
__MEMORY__
local function forget_slot(i) handlers.mem_forget(model['mem.items'][i+1].token) end
fail_write='memory.json'
remember('save-fail','memory_save',{text='Must not be reported as saved'})
assert(not replies['save-fail'].ok and #for_her().facts==0 and store['memory.json']==nil)
assert(text['mem.error']:find('Could not save memory',1,true))
fail_write=nil
remember('save','memory_save',{text='  Prefiero café y notas en español.  '})
assert(replies.save.ok and store['memory.json'].facts[1].text=='Prefiero café y notas en español.')
local id=store['memory.json'].facts[1].id
remember('duplicate','memory_save',{text='Prefiero café y notas en español.'})
assert(#store['memory.json'].facts==1)
remember('recall','memory_recall',{query='café español'})
assert(replies.recall.ok and replies.recall.text:find(id,1,true))
remember('note','memory_learn',{title='Abrir mis notas',when='Cuando busco apuntes',how='Abre el buscador y escribe notas.'})
remember('replace','memory_learn',{title='Abrir mis notas',when='Al estudiar',how='Busca la carpeta Apuntes.'})
assert(#store['memory.json'].notes==1)
remember('read','memory_read',{title='mis notas'})
assert(replies.read.ok and replies.read.text:find('Busca la carpeta Apuntes.',1,true))
fail_write='memory.json'
remember('replace-fail','memory_learn',{title='Abrir mis notas',when='Lost replacement',how='Must not replace the saved note'})
assert(not replies['replace-fail'].ok)
remember('read-again','memory_read',{title='mis notas'})
assert(replies['read-again'].text:find('Busca la carpeta Apuntes.',1,true))
remember('forget-fail','memory_forget',{id=id})
assert(not replies['forget-fail'].ok and #for_her().facts==1 and #store['memory.json'].facts==1)
show_memory();forget_slot(1)
assert(#for_her().notes==1 and #store['memory.json'].notes==1)
fail_write=nil
local prompt=for_her()
assert(#prompt.facts==1 and #prompt.notes==1 and prompt.notes[1].how==nil)
remember('forget','memory_forget',{id='['..id..']'})
assert(replies.forget.ok and #store['memory.json'].facts==0)
show_memory();forget_slot(0)
assert(#store['memory.json'].notes==0)
rows={{kind=1,text='Voy al taller el viernes.'},{kind=2,text='Entendido, al taller el viernes.'},{kind=4,text='pending action'}}
assert(keep_talk())
local names=talks()
assert(#names==1 and #store[names[1]].rows==2)
local first=names[1]
rows={{kind=1,text='Second archive in the same second'}}
assert(keep_talk())
names=talks()
assert(#names==2 and names[1]~=first and names[2]==first)
assert(store[first].rows[1].text=='Voy al taller el viernes.')
assert(store[names[1]].rows[1].text=='Second archive in the same second')
-- Failed saves do not prune archives or throw away the current conversation.
for i=1,301 do store[string.format('chat-20260101-%06d.json',i)]={rows={}} end
fail_write='*';rows={{kind=1,text='Keep this conversation open'}}
assert(not keep_talk() and #talks()==303 and rows[1].text=='Keep this conversation open')
fail_write=nil
fail_list=true;assert(not keep_talk());fail_list=false
assert(keep_talk() and #talks()==300)
rows={{kind=1,text='¿Qué dije del taller?'}}
remember('search','memory_search',{query='taller viernes'})
assert(replies.search.ok and replies.search.text:find('Voy al taller el viernes.',1,true))
store['settings.json']={keep=true};store['chat-other.json']={keep=true}
handlers.mem_clear_talks()
assert(fact['mem.sure']==true and #talks()==300)
timers[#timers].run()
assert(fact['mem.sure']==false and #talks()==300)
fail_remove=first
handlers.mem_clear_talks();handlers.mem_clear_talks()
assert(#talks()==1 and talks()[1]==first and fact['mem.kept']==1)
assert(text['mem.error']:find('could not be deleted',1,true))
fail_remove=nil
handlers.mem_clear_talks();handlers.mem_clear_talks()
assert(#talks()==0 and fact['mem.sure']==false and store['settings.json'].keep and store['chat-other.json'].keep)
remember('empty','memory_save',{text=' '});assert(not replies.empty.ok)
remember('unknown','memory_read',{title='Missing'});assert(not replies.unknown.ok)
store['chat-20200101-000000.json']={broken=true}
remember('unreadable','memory_search',{query='missing match'})
assert(not replies.unreadable.ok and replies.unreadable.text:find('Search incomplete',1,true))
store['chat-20200101-000000.json']=nil
fail_list=true
remember('listing','memory_search',{query='missing match'})
assert(not replies.listing.ok and replies.listing.text:find('Could not read saved conversations',1,true))
fail_list=false
-- Every bounded record remains reachable without allocating 300 scene rows.
for i=1,200 do remember('fact-'..i,'memory_save',{text='Fact '..i}) end
for i=1,100 do remember('note-'..i,'memory_learn',{title='Note '..i,how='Do this'}) end
assert(fact['mem.pages']==13 and #model['mem.items']==24)
local visible={}
local old_token=model['mem.items'][1].token
for page=1,13 do
    assert(fact['mem.page']==page and #model['mem.items']<=24)
    for _,item in ipairs(model['mem.items']) do assert(not visible[item.text]);visible[item.text]=true end
    if page<13 then handlers.mem_page(1) end
end
local count=0 for _ in pairs(visible) do count+=1 end
assert(count==300 and visible['Fact 1'] and visible['Note 1'])
handlers.mem_forget(old_token)
assert(#for_her().facts==200 and #for_her().notes==100,'stale row deleted a different memory')
handlers.mem_page(1);assert(fact['mem.page']==13)
-- Delete the last page and verify page clamping and identity mapping.
for _=1,12 do forget_slot(0) end
assert(fact['mem.page']==12 and fact['mem.pages']==12 and #for_her().notes==88)
handlers.mem_page(-1);assert(fact['mem.page']==11)
log('PASS: shared chat memory durable failures, same-second archives, pruning, partial deletion and all 300 paged records')
'''.replace('__MEMORY__',source[start:end])
run_checks(args,checks,'PASS: shared chat memory','chat-memory')
