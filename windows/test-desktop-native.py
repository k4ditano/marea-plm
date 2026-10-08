"""Native generated notification gestures against owned in-memory data; no OS notifications changed."""
from pathlib import Path
import os,re,json,subprocess,argparse,tempfile
parser=argparse.ArgumentParser(description="Exercise generated desktop notification gestures with owned in-memory data.")
parser.add_argument("--binary",type=Path,required=True)
args=parser.parse_args()
binary=args.binary.resolve()
marea=Path(__file__).resolve().parents[1]; work=Path(tempfile.mkdtemp(prefix='marea controls native '))
s=(marea/'marea-desktop.plm').read_text(encoding='utf-8')
for folder in ['common','lang','shaders','assets','wardrobe']: s=s.replace('"'+folder+'/', '"'+(marea/folder).as_posix()+'/')
s=s.replace('scene Marea {','scene UXControls {\n    fact fixture_ready = false\n    fact fixture_opened = 0\n    fact fixture_dismissed = 0')
s=s.replace('    surface {','    surface {\n        kind: window',1)
s=re.sub(r'        screens: each max \d+', '', s, count=1)
s,count=re.subn(r'(?m)^        open: swim\.here > 0\.01 or hosts\.here$', '        open: true', s, count=1)
assert count == 1, 'The notification fixture must keep its own surface open'
s=s.replace('        reserve: 72 while taking_room','',1)
s=s.replace('level: top, overlay while open or tray_open or menu_open or reel_open','level: overlay',1)
for expr in ['open or tray_open or menu_open or reel_open or searching','tide.on','adventuring and screen.index == adv_screen','tuck > 0.01 and screen.index == nook_screen']: s=s.replace('open: '+expr,'open: false')
s=s.replace('    // ── where she lives','    box { from: 0, 0; size: 820, 680; color: #e0e5e6 }\n    // ── where she lives',1)
s=s.replace('    service media as playback { playing: bool; title: text; artist: text }','    fact playback.playing = false\n    text playback.title = "Owned media fixture"\n    text playback.artist = "Native audio validation"')
(work/'ux-controls.plm').write_text(s,encoding='utf-8')
logic=(marea/'marea-desktop.luau').read_text(encoding='utf-8')
prelude=r'''
local real_sys = sys
local fixture_list, fixture_watch = {}, nil
for id = 1, 8 do fixture_list[id] = {id=id,app="SYSTEM",title="Aviso de prueba " .. id,body="Notificación local de validación",time=os.time(),actions={{key="open-app"}}} end
local sys = setmetatable({
    watch = function(name, callback)
        if name == "notifications" then fixture_watch = callback; after(500, function() callback(fixture_list) end); return true end
        if name == "notifications.state" then after(100, function() callback({access="allowed"}) end); return true end
        if name == "window" then
            after(600, function()
                local list = {}; for id = 1, 6 do list[id] = {id=id,title="Aplicación " .. id, minimized=true,icon=""} end
                callback({list=list})
            end); return true
        end
        if name == "apps" or name == "tray" then callback({}); return true end
        if name == "media" then
            return real_sys.watch(name, function(value)
                if tostring(value.player or ""):find("org.pleamar.validation.media.",1,true) == 1 then
                    callback(value); text["playback.title"] = value.title; text["playback.artist"] = value.artist; fact["playback.playing"] = value.playing
                else callback({available=false}) end
            end)
        end
        return real_sys.watch(name, callback)
    end,
    call_async = function(name,args,done)
        if name == "notifications.dismiss" then
            fact.fixture_dismissed += 1
            for i=#fixture_list,1,-1 do if fixture_list[i].id == args[1] then table.remove(fixture_list,i) end end
            after(60,function() done("",0); fixture_watch(fixture_list) end); return
        end
        if name == "notifications.invoke" then fact.fixture_opened += 1; done("",0); return end
        if name == "hotkeys.bind" or name == "hotkeys.unbind" then done("",0); return end
        if name:find("session.",1,true)==1 or name:find("window.",1,true)==1 then done("Disabled in owned fixture",1); return end
        return real_sys.call_async(name,args,done)
    end,
}, {__index=real_sys})
'''
post='''
after(1000,function()
    fact.language = "spanish"
    fact.needed = true
    fact.open = false
    fact.tray_open = true
    fact.filter = 4
    fact.fixture_ready = true
end)
'''
post += '\nafter(10000,function()\n    assert(fact.fixture_opened == 1, "a row click did not open exactly once")\n    assert(fact.fixture_dismissed == 1, "a row drag did not dismiss exactly once")\n    assert(fact["n.4"] == 7 and fact["alive.1"], "dismissed slot or counter was not refilled")\n    assert(math.abs(fact["flung.1"] or 0) < .01, "new row retained the old fling")\n    log("PASS: native generated notification row click/drag, slot reset and remaining count")\nend)\n'
(work/'ux-controls.luau').write_text(prelude+logic+post,encoding='utf-8')
env=dict(os.environ,APPDATA=str(work/'state'),PLEAMAR_SOCKET_DIR='ux-controls-test',PLEAMAR_NO_RELAUNCH='1',MAREA_SEARCH_HOTKEY='',PLEAMAR_TEST_WINDOWS='1')
result=subprocess.run([str(binary),'--scene',str(work/'ux-controls.plm'),'--no-hud','--stall','0','--seconds','12',
    '--mouse','436,187@2800 down@3000 up@3300 down@3900 320,187@4200 220,187@4500 up@4700'],
    cwd=marea,env=env,capture_output=True,text=True,encoding='utf-8',timeout=35,creationflags=subprocess.CREATE_NO_WINDOW)
output=result.stdout+result.stderr
(work/'native.log').write_text(output,encoding='utf-8')
assert result.returncode==0 and 'PASS: native generated notification' in output and 'runtime error:' not in output, output[-5500:]
print(next(line for line in output.splitlines() if 'PASS: native generated notification' in line))
print('Evidence:',work)
