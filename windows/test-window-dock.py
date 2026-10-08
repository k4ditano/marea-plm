"""Dock geometry, capability gating and owned scene lifetime, without desktop input."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
geometry = r'''
local handlers, requests = {}, {}
local fact, text = {}, {}
local screen = "\\\\.\\DISPLAY1"
local values = {good={{name=screen,scale=1.25,bounds={x=-1920,y=210,width=1920,height=1080},work={x=-1920,y=210,width=1920,height=1020}}}, missing={}}
local json = {decode=function(key) assert(values[key]);return values[key] end}
local sys = {ask=function(service,key) assert(service=="env");return key=="MAREA_LOCALE" and "es" or screen end}
local function tr(value) return value end
local function on(name,callback) handlers[name]=callback end
local function run(command,args,callback) assert(command=="pleamar-wm"); requests[#requests+1]={args=args,done=callback} end
__MODULE__
assert(fact.locale=="es" and requests[1].args[1]=="monitors")
handlers["fact:screen.width"]();handlers["fact:screen.height"]()
assert(#requests==1)
requests[1].done("good",0)
assert(fact.dock_ready and fact.dock_left==0 and fact.dock_width==1536 and fact.dock_bottom==48 and #requests==2)
requests[1].done("missing",0);assert(fact.dock_ready and #requests==2)
requests[2].done("missing",0);assert(not fact.dock_ready and text.dock_status~="")
values.good[1].scale=2
values.good[1].work.x=-1840;values.good[1].work.width=1840
handlers["fact:screen.width"]();requests[3].done("good",0)
assert(fact.dock_ready and fact.dock_left==40 and fact.dock_width==920 and fact.dock_bottom==30)
fact.dock_menu=3;handlers["text:win.dock.0.3.name"]();assert(fact.dock_menu==-1)
fact.dock_menu=2;handlers["fact:win.docks.0"]();assert(fact.dock_menu==-1)
handlers.dock_close();handlers.dock_close();assert(#requests==4)
assert(table.concat(requests[4].args,",")=="--say,windows-dock,quit")
requests[4].done("refused",1);assert(text.dock_status:find("could not close",1,true))
handlers.dock_close();assert(#requests==5);requests[5].done("",0)
handlers["fact:screen.width"]();assert(#requests==5)
log("PASS: dock geometry uses physical work areas and DPI, coalesces refresh, invalidates stale menus and handles close failures")
'''
run_checks(args, geometry.replace('__MODULE__', (root / 'tools/windows-dock.luau').read_text(encoding='utf-8')), 'PASS: dock geometry', 'dock-geometry')

adapter = r'''
local handlers, requests, children, notices, timers = {}, {}, {}, {}, {}
local entries, hooks, fact = {{id="other"}}, {}, {locale="es"}
local screen = "\\\\.\\DISPLAY1"
local value = {running=true,automatic_layouts=true,window_overview=true,monitors={{name=screen}}}
local json = {decode=function() return value end}
local function tr(s) return s end
local function on(name,callback) handlers[name]=callback end
local function after(ms,callback) assert(ms==2000);timers[#timers+1]=callback end
local function run(command,args,done,options) assert(command=="pleamar-wm");requests[#requests+1]={args=args,done=done,options=options} end
local function spawn(command,args,line,done,options)
    assert(command=="pleamar-wm" and args[2]=="tools/windows-dock.plm")
    assert(args[4]==screen and args[6]==screen and args[7]=="--window-actions")
    assert(options.env.MAREA_LOCALE=="es" and options.env.MAREA_DOCK_MONITOR==screen)
    assert(options.env.PLEAMAR_SOCKET_DIR:match("^marea%-dock%-"))
    children[#children+1]={line=line,done=done,endpoint=options.env.PLEAMAR_SOCKET_DIR}
end
local install=(function() __MODULE__ end)()
install(run,hooks,entries,function() end,function() return screen end,function(message) notices[#notices+1]=message end,spawn)
requests[1].done("status",0)
assert(not hooks.windows_wm_allowed("Application dock") and #entries==4)
value.application_dock=true;handlers["fact:menu_open"](true);requests[2].done("status",0)
assert(hooks.windows_wm_allowed("Application dock") and entries[5].title=="Show application dock")
hooks.windows_dock();assert(#children==1 and entries[5].title=="Hide application dock")
hooks.windows_dock();hooks.windows_dock();assert(#requests==3 and #children==1)
assert(table.concat(requests[3].args,",")=="--say,windows-dock,quit")
assert(requests[3].options.env.PLEAMAR_SOCKET_DIR==children[1].endpoint)
requests[3].done("not listening yet",1);assert(#notices==0)
timers[1]();assert(#notices==1)
hooks.windows_dock();assert(#requests==4);requests[4].done("bye",0)
hooks.windows_dock();assert(#children==1)
children[1].done("",0);assert(entries[5].title=="Show application dock")
timers[2]();assert(#notices==1)
hooks.windows_dock();assert(#children==2)
assert(children[2].endpoint~=children[1].endpoint)
children[1].done("late",1);assert(entries[5].title=="Hide application dock" and #notices==1)
children[2].line("windows dock: app refused");assert(#notices==2)
children[2].line("windows dock metadata: a catalog window exited");assert(#notices==2)
-- Hide stays available after losing the session, until the owned dock exits.
value={running=false};handlers["fact:menu_open"](true);requests[5].done("status",0)
assert(#entries==2 and entries[2].title=="Hide application dock")
hooks.windows_dock();requests[6].done("pipe disconnected",1);children[2].done("",0)
timers[3]();assert(#notices==2,"successful owned exit produced a stale close error")
assert(#entries==1 and not hooks.windows_wm_allowed("Application dock"))
log("PASS: Marea dock capability gate, monitor/locale selection, open/hide ownership, errors and stale callbacks")
'''
run_checks(args, adapter.replace('__MODULE__', (root / 'windows/window-manager.luau').read_text(encoding='utf-8')), 'PASS: Marea dock capability', 'dock-adapter')
