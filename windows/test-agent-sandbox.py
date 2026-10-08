"""Exercise the real Windows worker boundary using only owned fixtures."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--host', type=Path, required=True)
parser.add_argument('--node', type=Path, required=True)
parser.add_argument('--child-probe', type=Path, required=True)
parser.add_argument('--network', action='store_true', help='Also verify public HTTPS; omitted in offline CI')
parser.add_argument('--output', type=Path)
args = parser.parse_args()
assert os.name == 'nt', 'This test requires native Windows'
repo = Path(__file__).resolve().parents[1]
temp = Path(tempfile.gettempdir()).resolve()
bundle = Path(tempfile.mkdtemp(prefix='marea aislamiento ñ ', dir=temp)).resolve()
assert bundle.parent == temp and bundle.name.startswith('marea aislamiento ñ ')
(bundle/'bin').mkdir(); (bundle/'app/agent').mkdir(parents=True); (bundle/'state').mkdir()
host = bundle/'bin/marea-agent.exe'
runtime = bundle/'bin/node.exe'
shutil.copy2(args.host.resolve(), host); shutil.copy2(args.node.resolve(), runtime)
shutil.copy2(repo/'windows/fixtures/agent-sandbox-probe.mjs', bundle/'app/agent/sandbox-probe.mjs')
shutil.copy2(repo/'agent/state-image.mjs', bundle/'app/agent/state-image.mjs')
private = bundle/'private.txt'; private.write_text('Owned external fixture, not a user file.', encoding='utf-8')
request = {'privateFile':str(private), 'outsideWrite':str(bundle/'forbidden.txt'), 'network':args.network}
flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
command = [str(host),'--probe','--state',str(bundle/'state')]
env = dict(os.environ, MAREA_TEST_SECRET='fixture-secret-not-inherited', NODE_OPTIONS='--trace-warnings', MAREA_AGENT_TRACE='1')
report = {'network_requested':args.network, 'checks':{}}
kernel = c.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];kernel.WaitForSingleObject.restype=w.DWORD
kernel.CloseHandle.argtypes=[w.HANDLE]
security = c.WinDLL('advapi32',use_last_error=True)
security.GetFileSecurityW.argtypes=[w.LPCWSTR,w.DWORD,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)]
def acl(path):
    length=w.DWORD()
    security.GetFileSecurityW(str(path),4,None,0,c.byref(length))
    assert length.value
    buffer=c.create_string_buffer(length.value)
    assert security.GetFileSecurityW(str(path),4,buffer,len(buffer),c.byref(length)), c.WinError(c.get_last_error())
    return bytes(buffer)
def run(request=request):
    return subprocess.run(command,input=json.dumps(request),capture_output=True,text=True,encoding='utf-8',env=env,timeout=35,creationflags=flags)
try:
    result=run()
    assert result.returncode==0, result.stderr
    data=json.loads(result.stdout)
    names=['stateWrite','codeRead','codeWriteDenied','permissionCacheWriteDenied','outsideReadDenied','outsideWriteDenied','cleanEnvironment','imageRoundTrip']
    if args.network: names.append('network')
    for name in names:
        assert data.get(name) is True, (name,data)
        report['checks'][name]=True
    assert not (bundle/'forbidden.txt').exists()
    report['node_memory_bytes']=data['memory']['rss']

    # The first repeat adopts the worker's newly created files. Thereafter the
    # real LPAC worker keeps its permissions without rewriting identical ACLs.
    for repeat in range(5):
        result=run();assert result.returncode==0,result.stderr
        repeated=json.loads(result.stdout)
        assert all(repeated.get(name) is True for name in names),repeated
    writes=re.search(r'security updates \((\d+) writes\)',result.stderr)
    assert writes and int(writes[1])==0,result.stderr
    report['checks']['unchangedStateNeedsNoSecurityWrites']=True
    report['successful_immediate_restarts']=5

    # A persistent, idle worker must die when its owner disappears.
    child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=env,creationflags=flags)
    handle=None
    try:
        pending=queue.Queue()
        threading.Thread(target=lambda:pending.put(child.stdout.readline()),daemon=True).start()
        child.stdin.write(json.dumps(dict(request,network=False,hold=True)));child.stdin.close()
        data=json.loads(pending.get(timeout=15))
        handle=kernel.OpenProcess(0x100000,False,data['pid'])
        assert handle and kernel.WaitForSingleObject(handle,0)==258, 'worker was not alive before owner termination'
        child.terminate();child.wait(timeout=5)
        assert kernel.WaitForSingleObject(handle,5000)==0, 'worker survived its owner'
        report['checks']['ownerTerminationKillsWorker']=True
    finally:
        if handle: kernel.CloseHandle(handle)
        if child.poll() is None: child.kill();child.wait(timeout=5)
        child.stdout.close();child.stderr.close()

    # Use CreateProcessW directly: Node/libuv maps Windows error 367 to UNKNOWN.
    # This fixture checks the exact OS denial and the active mitigation policy.
    shutil.copy2(args.child_probe.resolve(),runtime)
    result=run()
    data=json.loads(result.stdout)
    assert result.returncode==0 and data.get('win32Error')==367 and data.get('childDenied') is True, (result.stderr,data)
    report['checks']['childProcessBlocked']=True
    report['child_policy']=data

    before=acl(private)
    link=bundle/'state/hard-link.txt'
    os.link(private,link)
    try:
        result=run()
        assert result.returncode==3 and 'hard link' in result.stderr, result.stderr
        assert acl(private)==before, 'external file ACL changed'
        report['checks']['hardLinkRejectedWithoutAclChange']=True
    finally: link.unlink()

    outside=bundle/'outside-directory';outside.mkdir()
    before=acl(outside)
    junction=bundle/'state/junction'
    # Node's native junction creation needs no symlink privilege or Unix tools.
    clean_env=dict(os.environ);clean_env.pop('NODE_OPTIONS',None)
    subprocess.run([str(args.node.resolve()),'-e','require("node:fs").symlinkSync(process.argv[1], process.argv[2], "junction")',str(outside),str(junction)],check=True,capture_output=True,env=clean_env,creationflags=flags)
    try:
        result=run()
        assert result.returncode==3 and 'reparse point' in result.stderr, result.stderr
        assert acl(outside)==before, 'external directory ACL changed'
        report['checks']['junctionRejectedWithoutAclChange']=True
    finally: os.rmdir(junction)
    report['passed']=True
finally:
    result=subprocess.run([str(host),'--remove-profile'],capture_output=True,text=True,encoding='utf-8',timeout=15,creationflags=flags)
    report['profile_cleanup_exit']=result.returncode
    assert result.returncode==0, result.stderr
    if args.output: args.output.resolve().write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Only this freshly-created, verified test directory is removed.
    assert bundle.parent==temp and bundle.name.startswith('marea aislamiento ñ ')
    shutil.rmtree(bundle)
print(json.dumps(report,indent=2))
