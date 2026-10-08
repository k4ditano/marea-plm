"""Measure the real signed-out SDK in isolated state, without opening any desktop window."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from process_memory import Reader


class ProcessEntry(c.Structure):
    _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('pid', w.DWORD),
                ('heap', c.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                ('parent', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD),
                ('name', w.WCHAR * 260)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New directory retained for measurements and isolated state')
    parser.add_argument('--seconds', type=int, default=15, help='Idle sampling seconds per launch, 5..120')
    parser.add_argument('--cycles', type=int, default=3, help='Repeated SDK starts, 1..10')
    args = parser.parse_args()
    if os.name != 'nt' or not 5 <= args.seconds <= 120 or not 1 <= args.cycles <= 10:
        parser.error('Use native Windows, 5..120 seconds and 1..10 cycles.')
    package, output = args.package.resolve(strict=True), args.output.resolve()
    host = package / 'bin/marea-agent.exe'
    assert host.is_file(), 'A complete native AI package is required'
    output.mkdir(parents=True, exist_ok=False)
    local = output / 'local'
    local.mkdir()
    env = dict(os.environ, LOCALAPPDATA=str(local))
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    kernel = c.WinDLL('kernel32', use_last_error=True)
    memory_reader = Reader()
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        method = getattr(kernel, name)
        method.argtypes = [w.HANDLE, c.POINTER(ProcessEntry)]
        method.restype = w.BOOL
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.WaitForSingleObject.restype = w.DWORD
    kernel.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4
    kernel.GetProcessTimes.restype = w.BOOL
    kernel.GetProcessHandleCount.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
    kernel.GetProcessHandleCount.restype = w.BOOL

    def node_handle(parent):
        snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
        if snapshot in (None, c.c_void_p(-1).value): raise c.WinError(c.get_last_error())
        try:
            entry = ProcessEntry()
            entry.dwSize = c.sizeof(entry)
            more = kernel.Process32FirstW(snapshot, c.byref(entry))
            while more:
                if entry.parent == parent and entry.name.lower() == 'node.exe':
                    handle = kernel.OpenProcess(0x100410, False, entry.pid)
                    if not handle: raise c.WinError(c.get_last_error())
                    return handle
                more = kernel.Process32NextW(snapshot, c.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        raise RuntimeError('The owned host has no live Node worker after ready')

    def metrics(handle):
        created, ended, system, user = [w.FILETIME() for _ in range(4)]
        handles = w.DWORD()
        for ok in (kernel.GetProcessTimes(handle, c.byref(created), c.byref(ended), c.byref(system), c.byref(user)),
                   kernel.GetProcessHandleCount(handle, c.byref(handles))):
            if not ok: raise c.WinError(c.get_last_error())
        return {'cpu_seconds': sum((v.dwHighDateTime << 32) | v.dwLowDateTime for v in (system, user)) / 1e7,
                **memory_reader.read(handle), 'handles': handles.value}

    report = {'complete': False, 'package': str(package), 'cycles': [],
              'scope': 'Real full SDK signed out and idle; separate validation profile and fresh account state. No model, Marea UI or desktop input.'}
    child = None
    try:
        for cycle in range(args.cycles):
            events = queue.Queue()
            began = time.monotonic()
            with (output / f'worker-{cycle}.log').open('w', encoding='utf-8') as errors:
                child = subprocess.Popen([str(host), '--validate-worker'], env=env, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=errors, text=True, encoding='utf-8', creationflags=flags)
                def read_lines(stream, channel):
                    for line in stream: channel.put(line)
                    channel.put(None)
                threading.Thread(target=read_lines, args=(child.stdout, events), daemon=True).start()
                child.stdin.write('{"type":"start","locale":"en","history":[]}\n')
                child.stdin.flush()
                line = events.get(timeout=180)
                event = json.loads(line) if line else None
                assert event and event.get('type') == 'ready' and event.get('usable') is False and event.get('reason') == 'signed_out', event
                ready_seconds = time.monotonic() - began
                handle = node_handle(child.pid)
                try:
                    before = metrics(handle)
                    points = []
                    began_idle = time.monotonic()
                    while time.monotonic() - began_idle < args.seconds:
                        time.sleep(min(1, max(.01, args.seconds - (time.monotonic() - began_idle))))
                        points.append(metrics(handle))
                    elapsed = time.monotonic() - began_idle
                    record = {'ready_seconds': round(ready_seconds, 3), 'idle_seconds': round(elapsed, 3),
                              'initial': before, 'final': points[-1], 'samples': points,
                              'idle_cpu_one_core_percent': round(100 * (points[-1]['cpu_seconds'] - before['cpu_seconds']) / elapsed, 3)}
                    child.stdin.write('{"type":"shutdown"}\n')
                    child.stdin.close()
                    assert child.wait(timeout=10) == 0
                    assert kernel.WaitForSingleObject(handle, 5000) == 0, 'owned Node outlived its host'
                    record['node_exited'] = True
                    report['cycles'].append(record)
                    print(json.dumps({k:v for k,v in record.items() if k != 'samples'}), flush=True)
                finally:
                    kernel.CloseHandle(handle)
        report['complete'] = True
    finally:
        if child and child.poll() is None: child.kill(); child.wait(timeout=10)
        cleanup = subprocess.run([str(host), '--remove-validation-profile'], capture_output=True,
            encoding='utf-8', creationflags=flags, timeout=30)
        report['profile_cleanup_exit'] = cleanup.returncode
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if cleanup.returncode: raise RuntimeError('Validation profile cleanup failed: ' + cleanup.stderr)
    print('PASS: full signed-out SDK measurements and owned process/profile cleanup; account and interactive workloads are not covered.')


if __name__ == '__main__': main()
