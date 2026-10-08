"""Native WM menus reflect real capabilities and acknowledgements."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('window-manager.luau').read_text(encoding='utf-8')
checks = r'''
local handlers, requests, notices, entries, hooks = {}, {}, {}, {{id="desktop"}}, {in_wm=false}
local replies = {}
local json = {decode=function(key) assert(replies[key]); return replies[key] end}
local function tr(s) return s end
local function on(name, callback) handlers[name]=callback end
local changed = 0
local fact = {locale="es"}
local screen = "\\\\.\\DISPLAY2"
local children = {}
local function spawn(name,args,line,done,options)
    assert(name=="pleamar-wm" and args[1]=="--scene" and args[2]=="tools/windows-overview.plm")
    assert(args[3]=="--screen" and args[4]==screen and args[5]=="--preview-monitor" and args[6]==screen)
    assert(args[7]=="--window-actions" and options.cwd=="." and options.errors==true and options.env.MAREA_LOCALE=="es")
    children[#children+1]={line=line,done=done}
    return #children
end
local function run(name, args, callback)
    assert(name=="pleamar-wm" and args[1]=="--say" and args[2]=="wm")
    requests[#requests+1]={command=args[3],done=callback}
end
local install=(function() __MODULE__ end)()
install(run,hooks,entries,function() changed+=1 end,function() return screen end,function(message) notices[#notices+1]=message end,spawn)
assert(#requests==1 and requests[1].command=="status")
requests[1].done("not installed",1)
assert(#entries==1 and #notices==0 and not hooks.windows_wm_allowed("Tiled or free windows"))
handlers["fact:menu_open"](true)
handlers["fact:menu_open"](true)
assert(#requests==2)
replies.good={running=true,automatic_layouts=true,monitors={{name=screen,tiled=false}}}
requests[2].done("good",0)
assert(#entries==3 and hooks.windows_wm_allowed("Tiled or free windows") and hooks.in_wm==false)
for _,title in ipairs({"Rain on the windows","Rain intensity","Snow on the windows","Ride a window"}) do
    assert(not hooks.windows_wm_allowed(title))
end
hooks.wm_free();hooks.wm_free()
assert(#requests==3 and requests[3].command=="toggle "..screen)
requests[3].done("good",0)
assert(#entries==3 and #notices==0)
screen="\\\\.\\DISPLAY1"
hooks.wm_free(); assert(#requests==3 and #notices==1)
screen="\\\\.\\DISPLAY2"
hooks.wm_free(); requests[4].done("native window refused resizing",1)
assert(#entries==1 and #notices==2 and not hooks.windows_wm_allowed("Tiled or free windows"))
requests[4].done("good",0) -- duplicate/stale completion cannot revive the session
assert(#entries==1)
handlers["fact:searching"](true)
requests[5].done("good",0)
assert(#entries==3 and hooks.windows_wm_allowed("Bring back every window"))
assert(not hooks.windows_wm_allowed("Window overview"))
replies.good.window_overview=true
handlers["fact:menu_open"](true);requests[6].done("good",0)
assert(#entries==4 and hooks.windows_wm_allowed("Window overview"))
screen="\\\\.\\DISPLAY1"
hooks.windows_overview(); assert(#children==0 and #notices==3)
screen="\\\\.\\DISPLAY2"
hooks.windows_overview();hooks.windows_overview()
assert(#children==1 and #notices==4)
children[1].line("capture failed");children[1].done("",1)
assert(#notices==5 and notices[5]:find("capture failed",1,true))
hooks.windows_overview();assert(#children==2)
children[1].done("",0);hooks.windows_overview();assert(#children==2)
children[2].done("",0);hooks.windows_overview();assert(#children==3)
-- Keyboard layout follows the native pointer monitor, not Marea's home monitor.
screen="\\\\.\\DISPLAY1"
hooks.windows_toggle_layout();hooks.windows_toggle_layout()
assert(#requests==7 and requests[7].command=="emit toggle_free" and #notices==6)
requests[7].done("good",0)
assert(hooks.windows_wm_allowed("Tiled or free windows"))
hooks.windows_toggle_layout();requests[8].done("pointer is outside this WM session",1)
assert(#notices==7 and notices[7]:find("pointer is outside this WM session",1,true))
assert(not hooks.windows_wm_allowed("Tiled or free windows"))
requests[8].done("good",0)
assert(not hooks.windows_wm_allowed("Tiled or free windows"))
-- A stale capability cache must not make the first shortcut after recovery a no-op.
hooks.windows_toggle_layout()
assert(#requests==9 and requests[9].command=="emit toggle_free")
requests[9].done("good",0)
assert(hooks.windows_wm_allowed("Tiled or free windows") and #notices==7)
hooks.windows_minimize();hooks.windows_minimize()
assert(#requests==10 and requests[10].command=="emit minimize")
requests[10].done("the active window is outside this WM session",1)
assert(#notices==8 and notices[8]:find("outside this WM session",1,true))
hooks.windows_restore_last()
assert(#requests==11 and requests[11].command=="emit restore_last")
requests[11].done("good",0)
assert(hooks.windows_wm_allowed("Tiled or free windows") and #notices==8)
-- Navigation is relative: rapid taps must reach each next window, in order.
hooks.windows_focus_next();hooks.windows_focus_next();hooks.windows_focus_previous()
assert(#requests==12 and requests[12].command=="emit focus_next")
requests[12].done("good",0)
assert(#requests==13 and requests[13].command=="emit focus_next")
requests[12].done("good",0);assert(#requests==13)
requests[13].done("good",0)
assert(#requests==14 and requests[14].command=="emit focus_previous")
requests[14].done("good",0)
hooks.windows_focus_next();hooks.windows_focus_next()
assert(#requests==15)
requests[15].done("foreground changed",1)
assert(#requests==15 and #notices==9, "failed navigation continued acting on a different foreground")
hooks.windows_close();hooks.windows_close()
assert(#requests==16 and requests[16].command=="emit close")
requests[16].done("good",0)
hooks.windows_fullscreen();hooks.windows_fullscreen()
assert(#requests==17 and requests[17].command=="emit fullscreen")
requests[17].done("fullscreen target is outside this WM session",1)
assert(#notices==10 and notices[10]:find("outside this WM session",1,true))
hooks.windows_fullscreen();assert(#requests==18);requests[18].done("good",0)
log("PASS: native WM capability menus, serialization, monitor scope and failed actions")
'''
run_checks(args, checks.replace('__MODULE__', module), 'PASS: native WM capability', 'window-manager')
