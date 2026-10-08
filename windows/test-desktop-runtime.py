"""Actual Marea adapter -> Luau native worker -> owned DISPLAY2 window capture."""
from pathlib import Path
import argparse, json, os, subprocess, sys, tempfile, time

if sys.platform != 'win32':
    raise SystemExit('This native integration test requires Windows and secondary DISPLAY2.')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--fixture-test-binary', type=Path, required=True, help='pleamar lib test executable containing the owned native fixture')
parser.add_argument('--output', type=Path, help='new evidence directory; must not already exist')
args = parser.parse_args()
review = Path(__file__).resolve().parents[1]
if args.output:
    out = args.output.resolve()
    out.mkdir(parents=False, exist_ok=False)
else:
    out = Path(tempfile.mkdtemp(prefix='marea desktop bridge ñ '))
fixture = out/'fixture'; fixture.mkdir()
binary = args.binary.resolve()
test = args.fixture_test_binary.resolve()
flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
env = dict(os.environ, APPDATA=str(out/'config'), LOCALAPPDATA=str(out/'local'), PLEAMAR_SOCKET_DIR='desktop-bridge-'+str(os.getpid()), PLEAMAR_NO_RELAUNCH='1')
result = {'out':str(out), 'screen':r'\\.\DISPLAY2', 'physical_input_sent':False}
child = subprocess.Popen([str(test),'--ignored','--exact','platform::windows_desktop::native_tests::owned_fixture'],
    env=dict(env,PLEAMAR_OWNED_DESKTOP_FIXTURE=str(fixture)),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=flags)
app = None
def ask(command):
    return subprocess.check_output([str(binary),'--say','bridge',command],env=env,text=True,encoding='utf-8',stderr=subprocess.DEVNULL,timeout=4,creationflags=flags).strip()
try:
    start=time.monotonic()
    while not (fixture/'state.json').exists():
        assert child.poll() is None, child.stderr.read().decode(errors='replace')
        assert time.monotonic()-start<12
        time.sleep(.05)
    # The fixture refuses to open unless DISPLAY2 is active and non-primary.
    scene=out/'bridge.plm'
    scene.write_text('''scene DesktopBridge {
    permissions { services: "desktop.*" }
    surface { size: 420, 130; anchor: bottom; keyboard: none }
    fact done = false
    fact ticks = 0
    fact bytes = 0
    text phase = "Comprobando captura nativa…"
    box { from: 0, 0; size: 420, 130; color: #142624; corner: 16 }
    text "Marea · enlace de escritorio" { at: 20, 20; size: 21; color: #ffffff }
    text "{phase}" { at: 20, 68; size: 14; color: #b4ebd6 }
    text "Luau · {ticks, 0}" { at: 20, 103; size: 12; color: #8b8f95 }
}''',encoding='utf-8')
    adapter=(review/'windows/desktop-agent.luau').read_text(encoding='utf-8')
    logic='local install = (function()\n'+adapter+'\nend)()\n'+'''
local dispatch = install(sys)
every(30,function() fact.ticks+=1 end)
after(100,function()
    dispatch("desktop_windows",{},function(ok,words)
        assert(ok,words)
        local id
        for line in words:gmatch("[^\\n]+") do
            if line:find("«Pleamar desktop fixture __PID__ —",1,true) then id=line:match("^(%d+)%s");break end
        end
        assert(id,"owned fixture was missing")
        dispatch("desktop_look",{pid=id},function(captured,message,extra)
            assert(captured,message)
            assert(extra.image.data:sub(1,8)=="iVBORw0K")
            assert(#extra.image.data>1000)
            fact.bytes=#extra.image.data
            dispatch("cancel",{},function() end)
            dispatch("desktop_type",{pid=id,text="must not be sent"},function(accepted,error)
                assert(not accepted and error:find("List windows",1,true))
                fact.done=true
                text.phase="Captura y cancelación verificadas"
            end)
        end)
    end)
end)
'''.replace('__PID__',str(child.pid))
    (out/'bridge.luau').write_text(logic,encoding='utf-8')
    with (out/'native.log').open('w',encoding='utf-8') as log:
        app=subprocess.Popen([str(binary),'--scene',str(scene),'--screen',r'\\.\DISPLAY2','--no-hud','--stall','0','--seconds','45'],env=env,stdout=log,stderr=log,creationflags=flags)
        start=time.monotonic()
        while time.monotonic()-start<35 and app.poll() is None:
            try:
                if ask('get done') in ('1','true'): break
            except (subprocess.SubprocessError,OSError): pass
            time.sleep(.1)
        result['facts']={key:ask('get '+key) for key in ('done','ticks','bytes')}
        assert result['facts']['done'] in ('1','true'),result
        result['seconds']=round(time.monotonic()-start,3)
        ask('quit'); app.wait(timeout=10)
        result['exit']=app.returncode
        assert app.returncode==0
        log.flush()
        output=(out/'native.log').read_text(encoding='utf-8')
        assert 'first frame' in output and 'runtime error:' not in output
        result['native_first_frame']=True
finally:
    if app and app.poll() is None:
        try: ask('quit');app.wait(timeout=4)
        except (subprocess.SubprocessError,OSError): app.kill();app.wait(timeout=4)
    (fixture/'control').write_text('quit')
    try: child.wait(timeout=4)
    except subprocess.TimeoutExpired: child.kill();child.wait(timeout=4)
    result['fixture_exit']=child.returncode
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
