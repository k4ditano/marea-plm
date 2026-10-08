"""Exercise shared memory logic through the real native files service, without a UI/account."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
out=args.output.resolve()
out.mkdir(parents=True,exist_ok=False)
from logic_test import shared_logic
source=shared_logic()
start=source.index('    -- ── her memory ──')
end=source.index('    -- ── the worker ──',start)
scene=out/'memory-native.plm'
scene.write_text('''scene MemoryTest {
 permissions { services: "files", "files.*" }
 surface { kind: window; size: 40, 40; keyboard: none; screens: "__memory_native_absent__" }
}
''',encoding='utf-8')
logic=r'''
local hooks={language={}}
local fact,text,model,rows,handlers,replies={},{},{},{},{},{}
local function tr(value) return value end
local function first_letters(s,n) local at=utf8.offset(s,n+1);return at and s:sub(1,at-1) or s end
local function add(kind,value,detail,state) rows[#rows+1]={kind=kind,text=value,detail=detail,state=state};return #rows end
local function finish_row(row,ok) rows[row].state=ok and 1 or 2 end
local function answer(id,ok,value) replies[id]={ok=ok,text=value} end
local function on(name,callback) handlers[name]=callback end
__MEMORY__
remember('saved','memory_save',{text='Recuerdo de prueba: café y 日本語.'})
assert(replies.saved.ok)
local saved=sys.ask('files.read','memory.json','json')
assert(#saved.facts==1 and saved.facts[1].text=='Recuerdo de prueba: café y 日本語.')
remember('noted','memory_learn',{title='Prueba nativa',when='Al validar Windows',how='Guardar, consultar y borrar.'})
assert(#sys.ask('files.read','memory.json','json').notes==1)
rows={{kind=1,text='El taller es el viernes.'},{kind=2,text='Nos vemos el viernes.'}}
keep_talk()
assert(#talks()==1)
rows={}
remember('found','memory_search',{query='taller viernes'})
assert(replies.found.ok and replies.found.text:find('El taller es el viernes.',1,true))
sys.call('files.write','settings.json',{sentinel='keep'})
handlers.mem_clear_talks();assert(#talks()==1)
handlers.mem_clear_talks();assert(#talks()==0)
assert(sys.ask('files.read','settings.json','json').sentinel=='keep')
remember('forgot','memory_forget',{id=saved.facts[1].id})
assert(replies.forgot.ok and #sys.ask('files.read','memory.json','json').facts==0)
assert(#sys.ask('files.read','memory.json','json').notes==1)
log('PASS: native shared memory files roundtrip')
'''.replace('__MEMORY__',source[start:end])
scene.with_suffix('.luau').write_text(logic,encoding='utf-8')
env=dict(os.environ,APPDATA=str(out/'roaming'),LOCALAPPDATA=str(out/'local'),
         XDG_DATA_HOME=str(out/'data'),PLEAMAR_NO_RELAUNCH='1',PLEAMAR_SOCKET_DIR='memory-test-'+str(os.getpid()))
result=subprocess.run([str(args.binary.resolve()),'--scene',str(scene),'--no-hud','--stall','0','--seconds','2'],
    env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20,
    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
trace=result.stdout+result.stderr
(out/'runtime.log').write_text(trace,encoding='utf-8')
assert result.returncode==0 and 'PASS: native shared memory files roundtrip' in trace,trace
assert 'first frame' not in trace and 'runtime error:' not in trace,trace
report={'passed':True,'real_files_service':True,'graphical_validation':False,'real_model':False,'physical_input':False}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS: native shared memory files roundtrip; isolated storage, no windows/account')
subprocess.run([sys.executable,str(root/'windows/test-chat-memory-errors.py'),
    '--binary',str(args.binary.resolve()),'--output',str(out/'errors')],check=True)
