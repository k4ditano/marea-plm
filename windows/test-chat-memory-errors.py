"""Actual file-service failures must not report saved or deleted memories."""
import argparse
import json
import os
from pathlib import Path
import ctypes
from ctypes import wintypes
import subprocess

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--binary',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
root=Path(__file__).resolve().parents[1]
from logic_test import shared_logic
source=shared_logic()
start=source.index('    -- ── her memory ──')
end=source.index('    -- ── the worker ──',start)
prefix=r'''
local hooks={language={}}
local fact,text,model,rows,handlers,replies={},{},{},{},{},{}
local os=table.clone(os)
os.date=function() return '20261005-120000' end
local function tr(value) return value end
local function first_letters(s,n) local at=utf8.offset(s,n+1);return at and s:sub(1,at-1) or s end
local function add(kind,value,detail,state) rows[#rows+1]={kind=kind,text=value,detail=detail,state=state};return #rows end
local function finish_row(row,ok) rows[row].state=ok and 1 or 2 end
local function answer(id,ok,value) replies[id]={ok=ok,text=value} end
local function on(name,callback) handlers[name]=callback end
local function emit() end
'''+source[start:end]
cases={
    'same-second':r'''
rows={{kind=1,text='Primera conversación: café y 日本語.'}}
assert(keep_talk());local first=talks()[1]
rows={{kind=1,text='Second conversation in the same second'}}
assert(keep_talk() and #talks()==2)
assert(sys.ask('files.read',first,'json').rows[1].text=='Primera conversación: café y 日本語.')
assert(sys.ask('files.read',talks()[1],'json').rows[1].text=='Second conversation in the same second')
''',
    'write-failure':r'''
remember('failed','memory_save',{text='Must not replace the previous memory'})
assert(not replies.failed.ok and #for_her().facts==1)
assert(sys.ask('files.read','memory.json','json').facts[1].text=='Keep this memory')
handlers.mem_forget(model['mem.items'][1].token)
assert(#for_her().facts==1 and #sys.ask('files.read','memory.json','json').facts==1)
assert(text['mem.error']:find('Could not save memory',1,true))
''',
    'archive-failure':r'''
rows={{kind=1,text='Keep this conversation'}}
assert(not keep_talk() and #talks()==1 and rows[1].text=='Keep this conversation')
assert(sys.ask('files.read','chat-20200101-000000.json','json').sentinel=='preserve')
''',
    'invalid-json':r'''
remember('failed','memory_save',{text='Do not overwrite unreadable memory'})
assert(not replies.failed.ok and text['mem.error']:find('Could not read memory',1,true))
assert(sys.ask('files.read','memory.json')=='{broken')
''',
    'invalid-schema':r'''
remember('failed','memory_save',{text='Do not overwrite invalid memory'})
assert(not replies.failed.ok and text['mem.error']:find('Could not read memory',1,true))
assert(sys.ask('files.read','memory.json','json').facts[1]=='invalid record')
''',
    'listing-error':r'''
local all,problem=talks()
assert(#all==0 and problem~=nil,'OS listing failure was reported as an empty archive')
rows={{kind=1,text='Keep this conversation'}}
assert(not keep_talk())
''',
}
if os.name=='nt':
    cases['partial-delete']=r'''
handlers.mem_clear_talks();handlers.mem_clear_talks()
assert(#talks()==1 and talks()[1]=='chat-20200101-000000.json')
assert(fact['mem.kept']==1 and text['mem.error']:find('could not be deleted',1,true))
'''
report={'passed':False,'cases':[],'real_files_service':True,'graphical':False,'input_sent':False}
for label,checks in cases.items():
    stage=out/label;stage.mkdir()
    scene=stage/'memory-native.plm'
    scene.write_text('''scene MemoryTest {
 permissions { services: "files", "files.*" }
 surface { kind: window; size: 40, 40; keyboard: none; screens: "__memory_native_absent__" }
}''',encoding='utf-8')
    scene.with_suffix('.luau').write_text(prefix+checks+"\nlog('PASS: native memory storage case')\n",encoding='utf-8')
    storage=stage/'roaming/pleamar/memory-native'
    if label=='listing-error':
        storage.parent.mkdir(parents=True);storage.write_text('Storage is not a directory',encoding='utf-8')
    else:
        storage.mkdir(parents=True)
    if label=='write-failure':
        (storage/'memory.json').write_text(json.dumps({'facts':[{'id':'f1','text':'Keep this memory'}],'notes':[],'next':2}),encoding='utf-8')
        (storage/'memory.json.new').mkdir()
    if label=='archive-failure':
        (storage/'chat-20200101-000000.json').write_text('{"sentinel":"preserve"}',encoding='utf-8')
        (storage/'chat-20261005-120000.json.new').mkdir()
    if label=='invalid-json': (storage/'memory.json').write_text('{broken',encoding='utf-8')
    if label=='invalid-schema': (storage/'memory.json').write_text('{"facts":["invalid record"]}',encoding='utf-8')
    protected=None
    if label=='partial-delete':
        protected=storage/'chat-20200101-000000.json'
        protected.write_text('{}',encoding='utf-8')
        (storage/'chat-20200102-000000.json').write_text('{}',encoding='utf-8')
        # Hold a read handle without FILE_SHARE_DELETE. Readonly attributes are
        # insufficient: recent Rust versions can remove readonly Windows files.
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,
            wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        held=kernel.CreateFileW(str(protected),0x80000000,3,None,3,0,None)
        assert held!=ctypes.c_void_p(-1).value,ctypes.get_last_error()
    env=dict(os.environ,APPDATA=str(stage/'roaming'),LOCALAPPDATA=str(stage/'local'),
        XDG_DATA_HOME=str(stage/'data'),PLEAMAR_NO_RELAUNCH='1',PLEAMAR_SOCKET_DIR='memory-test-'+str(os.getpid()))
    try:
        result=subprocess.run([str(a.binary.resolve()),'--scene',str(scene),'--no-hud','--stall','0','--seconds','2'],
            env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
    finally:
        if protected: assert kernel.CloseHandle(held)
    trace=result.stdout+result.stderr
    (stage/'runtime.log').write_text(trace,encoding='utf-8')
    assert result.returncode==0 and 'PASS: native memory storage case' in trace,trace
    # Deliberately failed native calls include "runtime error" in their caught
    # exception text. The final marker is reached only after all assertions.
    assert 'first frame' not in trace and 'panicked' not in trace,trace
    report['cases'].append(label)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
report['passed']=True
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS:',len(report['cases']),'native storage/archive cases; isolated files, no windows/account')
