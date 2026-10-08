"""Run Marea's real dock adapter with isolated session status and native child processes."""
from pathlib import Path
import argparse,ctypes as C,json,os,shutil,subprocess,time
from ctypes import wintypes as W

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary',type=Path,required=True)
parser.add_argument('--monitor',required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--ci-owned-desktop',action='store_true')
options=parser.parse_args()
if options.ci_owned_desktop:
    assert all(os.environ.get(k)==v for k,v in [('GITHUB_ACTIONS','true'),('RUNNER_ENVIRONMENT','github-hosted'),('PLEAMAR_WM_CI_DOCK','1')]), 'Primary output is restricted to the disposable GitHub-hosted test'
binary=options.binary.resolve(strict=True)
root=Path(__file__).resolve().parents[1]
output=options.output.resolve()
assert not output.exists(), 'Preserve earlier evidence'
flags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
screens=json.loads(subprocess.check_output([str(binary),'monitors'],encoding='utf-8',creationflags=flags))
screen=next((s for s in screens if s['name']==options.monitor and (options.ci_owned_desktop or not s['primary'])),None)
assert screen is not None, 'An explicit secondary monitor is required'
output.mkdir();(output/'tools').mkdir()
for suffix in ['plm','luau']:shutil.copy2(root/f'tools/windows-dock.{suffix}',output/f'tools/windows-dock.{suffix}')
env=dict(os.environ,PLEAMAR_CONFIG=str(output/'config'),APPDATA=str(output/'appdata'),LOCALAPPDATA=str(output/'local'),
    PLEAMAR_SOCKET_DIR='dock-owner-'+str(os.getpid()),PLEAMAR_NO_RELAUNCH='1',PATH=str(binary.parent)+os.pathsep+os.environ.get('PATH',''))
user=C.WinDLL('user32',use_last_error=True)
callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
for name,ret,args in [('SetProcessDpiAwarenessContext',W.BOOL,[W.HANDLE]),('GetForegroundWindow',W.HWND,[]),
    ('GetWindowThreadProcessId',W.DWORD,[W.HWND,C.POINTER(W.DWORD)]),('EnumWindows',W.BOOL,[callback,W.LPARAM]),
    ('IsWindowVisible',W.BOOL,[W.HWND]),('GetWindowRect',W.BOOL,[W.HWND,C.POINTER(W.RECT)])]:
    fn=getattr(user,name);fn.restype=ret;fn.argtypes=args
assert user.SetProcessDpiAwarenessContext(W.HANDLE(-4))
owners=[];owned=set();children=[]
report=dict(passed=False,monitor=screen,session_status_fixture=True,os_input=False,installed_product_changed=False,stages=[])
def windows(pid):
    result=[]
    @callback
    def visit(hwnd,_):
        current=W.DWORD();user.GetWindowThreadProcessId(hwnd,C.byref(current))
        if current.value==pid and user.IsWindowVisible(hwnd):result.append(hwnd)
        return True
    assert user.EnumWindows(visit,0)
    return result

def guard():
    pid=W.DWORD();user.GetWindowThreadProcessId(user.GetForegroundWindow(),C.byref(pid))
    assert pid.value not in owned, 'Owned scene took foreground'
    bounds=screen['bounds']
    for pid in owned:
        for hwnd in windows(pid):
            r=W.RECT();assert user.GetWindowRect(hwnd,C.byref(r))
            assert bounds['x']<=r.left<r.right<=bounds['x']+bounds['width']
            assert bounds['y']<=r.top<r.bottom<=bounds['y']+bounds['height']

def command(args,environment=env):
    r=subprocess.run([str(binary),*args],env=environment,cwd=output,capture_output=True,encoding='utf-8',creationflags=flags,timeout=6)
    if r.returncode or r.stdout.startswith('?'):raise RuntimeError(r.stderr+r.stdout)
    return r.stdout.strip()

def say(name,line,environment=env):return command(['--say',name,line],environment)

def wait(fn,label):
    until=time.monotonic()+20;last=None
    while time.monotonic()<until:
        guard()
        try:
            last=fn()
            if last:return last
        except (RuntimeError,subprocess.TimeoutExpired) as e:last=str(e)
        time.sleep(.08)
    raise RuntimeError(f'{label}: {last}')

module=(root/'windows/window-manager.luau').read_text(encoding='utf-8')
status=json.dumps(dict(running=True,automatic_layouts=True,window_overview=True,application_dock=True,monitors=[dict(name=screen['name'])]))
logic='local hooks, entries = {}, {}\nlocal actual_run, actual_spawn = run, spawn\nlocal function execute(command, args, done, options)\n    if args[1] == "--say" and args[2] == "wm" and args[3] == "status" then done([==[__STATUS__]==], 0)\n    else actual_run(command, args, done, options) end\nend\nlocal function start(command, args, line, done, options)\n    text.endpoint = options.env.PLEAMAR_SOCKET_DIR\n    return actual_spawn(command, args, line, done, options)\nend\nlocal install=(function() __MODULE__ end)()\ninstall(execute, hooks, entries, function()\n    fact.dock_open = false\n    for _,entry in ipairs(entries) do if entry.id=="windows.wm.dock" then fact.dock_open=entry.title=="Hide application dock" end end\nend, function() return [==[__MONITOR__]==] end, function(message) text.notice=message; log(message) end, start)\non("toggle", hooks.windows_dock)\n'
logic=logic.replace('__STATUS__',status).replace('__MONITOR__',screen['name']).replace('__MODULE__',module)
try:
    for name in ['dock-owner-a','dock-owner-b']:
        path=output/(name+'.plm')
        path.write_text('scene Owner { surface { size: 2, 2; anchor: center; keyboard: none; reserve: 0 } permissions { run: "pleamar-wm" } fact dock_open = false\n text endpoint = ""\n text notice = ""\n event toggle ->\n }',encoding='utf-8')
        path.with_suffix('.luau').write_text(logic,encoding='utf-8')
        subprocess.run([str(binary),'--check',str(path)],env=env,capture_output=True,creationflags=flags,check=True)
        with (output/(name+'.log')).open('wb') as log:
            process=subprocess.Popen([str(binary),'--scene',str(path),'--screen',screen['name'],'--no-hud','--stall','0','--seconds','90'],env=env,creationflags=flags,stdout=log,stderr=subprocess.STDOUT)
        owners.append((name,process));owned.add(process.pid)
        wait(lambda:say(name,'get dock_open') in ('false','0'),'owner ready')
        say(name,'emit toggle')
        wait(lambda:say(name,'get dock_open') in ('true','1'),'adapter opened')
        endpoint=wait(lambda:say(name,'get endpoint'),'child namespace').strip('"')
        child_env=dict(env,PLEAMAR_SOCKET_DIR=endpoint)
        wait(lambda:say('windows-dock','get dock_ready',child_env) in ('true','1'),'actual dock ready')
        found=json.loads(command(['agent','scenes'],child_env))
        assert len(found)==1 and found[0]['endpoint']=='windows-dock',found
        child=dict(pid=found[0]['pid'],endpoint=endpoint,environment=child_env)
        children.append(child);owned.add(child['pid']);guard()
    assert children[0]['endpoint']!=children[1]['endpoint']
    report['stages'].append('two-real-Luau-launches-use-separate-command-namespaces')
    say(owners[0][0],'emit toggle')
    wait(lambda:say(owners[0][0],'get dock_open') in ('false','0'),'first adapter exit callback')
    wait(lambda:not windows(children[0]['pid']),'first dock closed')
    assert say('windows-dock','get dock_ready',children[1]['environment']) in ('true','1')
    assert windows(children[1]['pid'])
    report['stages'].append('hiding-one-dock-keeps-the-other-alive')
    owners[1][1].kill();owners[1][1].wait(timeout=5)
    wait(lambda:not windows(children[1]['pid']),'dock ended with its owner')
    report['stages'].append('forced-owner-exit-cleans-its-dock')
    notice=say(owners[0][0],'get notice')
    report['notice']=notice
    assert notice in ('','""'), notice
    report.update(passed=True,foreground_owned_at_checks=False,children=[{k:c[k] for k in ['pid','endpoint']} for c in children])
finally:
    for name,process in owners:
        if process.poll() is None:
            try:say(name,'quit');process.wait(timeout=5)
            except Exception:process.kill();process.wait(timeout=5)
    deadline=time.monotonic()+5
    while any(windows(pid) for pid in owned) and time.monotonic()<deadline:time.sleep(.1)
    report['remaining_owned_windows']=[pid for pid in owned if windows(pid)]
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
assert not report['remaining_owned_windows']
print(json.dumps(report,indent=2))
