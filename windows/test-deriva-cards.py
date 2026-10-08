"""Rehearse current library cards on passive DISPLAY2 with an internal mouse script.

Only the owned scene receives simulated renderer events. No desktop input,
browser launch, account, worker or user library is involved.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def desktop_guard():
    user = c.WinDLL('user32', use_last_error=True)
    monitor_callback = c.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, c.POINTER(w.RECT), w.LPARAM)
    window_callback = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    class Monitor(c.Structure):
        _fields_ = [('size', w.DWORD), ('rect', w.RECT), ('work', w.RECT), ('flags', w.DWORD), ('name', w.WCHAR * 32)]
    for name, arguments, result in [
        ('SetThreadDpiAwarenessContext', [w.HANDLE], w.HANDLE),
        ('EnumDisplayMonitors', [w.HDC, c.POINTER(w.RECT), monitor_callback, w.LPARAM], w.BOOL),
        ('GetMonitorInfoW', [w.HANDLE, c.POINTER(Monitor)], w.BOOL),
        ('EnumWindows', [window_callback, w.LPARAM], w.BOOL),
        ('GetWindowThreadProcessId', [w.HWND, c.POINTER(w.DWORD)], w.DWORD),
        ('GetForegroundWindow', [], w.HWND), ('IsWindowVisible', [w.HWND], w.BOOL),
        ('GetWindowRect', [w.HWND, c.POINTER(w.RECT)], w.BOOL),
        ('GetWindowLongPtrW', [w.HWND, c.c_int], c.c_ssize_t),
        ('SetWindowLongPtrW', [w.HWND, c.c_int, c.c_ssize_t], c.c_ssize_t),
        ('EnableWindow', [w.HWND, w.BOOL], w.BOOL),
    ]:
        method = getattr(user, name); method.argtypes, method.restype = arguments, result
    previous = user.SetThreadDpiAwarenessContext(w.HANDLE(-4))
    assert previous, 'Per-monitor DPI awareness is required'

    def monitor():
        found = []
        @monitor_callback
        def visit(handle, _dc, _rect, _data):
            info = Monitor(); info.size = c.sizeof(info)
            if user.GetMonitorInfoW(handle, c.byref(info)) and info.name == r'\\.\DISPLAY2' and not info.flags & 1:
                found.append(info.rect)
            return True
        assert user.EnumDisplayMonitors(None, None, visit, 0) and len(found) == 1, 'Active non-primary DISPLAY2 is required'
        return found[0]

    def protect(pid):
        screen = monitor(); windows = []
        @window_callback
        def visit(handle, _data):
            owner = w.DWORD(); user.GetWindowThreadProcessId(handle, c.byref(owner))
            if owner.value == pid: windows.append(handle)
            return True
        assert user.EnumWindows(visit, 0)
        for handle in windows:
            owner = w.DWORD(); user.GetWindowThreadProcessId(handle, c.byref(owner))
            if owner.value != pid: continue
            if user.IsWindowVisible(handle):
                rect = w.RECT(); assert user.GetWindowRect(handle, c.byref(rect))
                assert screen.left <= rect.left < rect.right <= screen.right and screen.top <= rect.top < rect.bottom <= screen.bottom
            user.EnableWindow(handle, False)
            user.SetWindowLongPtrW(handle, -20, user.GetWindowLongPtrW(handle, -20) | 0x20)
    monitor()
    return user, previous, protect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.name == 'nt', 'This native desktop rehearsal requires Windows'
    marea = Path(__file__).resolve().parents[1]; binary = args.binary.resolve(strict=True)
    work = args.output.resolve(); work.mkdir(parents=True, exist_ok=False)
    source = (marea / 'marea-desktop.plm').read_text(encoding='utf-8')
    components = source[source.index('            component DriftButton'):source.index('            component DriftChip')]
    models = '\n'.join(re.search(r'(?s)model ' + name + r' max 6 \{.*?\}', source)[0] for name in ('drift', 'drift_spaces'))
    scene = work / 'deriva-card-window.plm'
    scene.write_text('import "' + (marea/'common/palette.plm').as_posix() + '"\nscene DerivaCards {\n' + '''
    surface { size: 520, 460; anchor: center; keyboard: none; level: overlay; rate: 30 }
    event drift_pick ->
    event drift_fav ->
    event drift_move ->
    event drift_bin ->
    event drift_to ->
    event drift_scroll ->
    fact page: none | drift = drift
    prop paging = 1
    fact drift.moving = -1
    fact drift.trash = false
    fact clicks = 0
    fact wheels = 0
    text opened = ""
    let amber = #edb86d
    box { from: 0, 0; size: 520, 460; color: #151616 }
''' + models + '\n' + components + '''
    zone box drift_area { from: 32, 80; size: 456, 312 }
    grid { at: 32, 80; columns: 3; gap: 12; width: 456; row: 150
        for d in drift { DriftCard(d) }
    }
    on scroll drift_area { emit drift_scroll(wheel) }
}
''', encoding='utf-8')
    scene.with_suffix('.luau').write_text('''
model.drift = {{title="YouTube · España 海", source="youtube", date="Today", glyph="Y", excerpt="",
    cr=0.6,cg=0.1,cb=0.1,thumb="",has_thumb=false,note=false,fav=false,in_space=false,
    link="https://www.youtube.com/watch?v=dQw4w9WgXcQ"}}
on("drift_pick", function(i)
    assert(i == 0, "An unused model slot received a click")
    fact.clicks += 1
    text.opened = model.drift[i + 1].link
end)
on("drift_scroll", function() fact.wheels += 1 end)
''', encoding='utf-8')
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    subprocess.run([str(binary),'--check',str(scene)], check=True, creationflags=flags)
    user, previous, protect = desktop_guard(); foreground = user.GetForegroundWindow()
    report = dict(passed=False, physical_input=False, browser_launched=False, screen=r'\\.\DISPLAY2',
        binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    env = dict(os.environ, PLEAMAR_CONFIG=str(work/'config'), PLEAMAR_SOCKET_DIR=f'deriva-cards-{os.getpid()}',
        PLEAMAR_NO_RELAUNCH='1', PLEAMAR_TEST_WINDOWS='1', PLEAMAR_DEBUG_ZONES='1')
    process = None
    try:
        with (work/'native.log').open('w',encoding='utf-8') as output:
            process = subprocess.Popen([str(binary),'--scene',str(scene),'--screen',r'\\.\DISPLAY2','--no-hud','--stall','0',
                '--seconds','7','--mouse','360,155@1000 click@1300 100,155@2000 click@2300 wheel-@2800',
                '--record','clicks,wheels,opened'], cwd=work,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=flags)
            deadline = time.monotonic()+40
            while process.poll() is None:
                assert time.monotonic() < deadline, 'Native rehearsal timed out'
                protect(process.pid); time.sleep(.05)
            assert process.returncode == 0
        content = (work/'native.log').read_text(encoding='utf-8')
        assert 'first frame' in content and 'runtime error' not in content and 'panicked' not in content, content[-4000:]
        rows = [line.split('\t') for line in content.splitlines() if '\t' in line]
        assert any(len(row)==4 and row[1:3]==['1.0000','1.0000'] and row[3].endswith('dQw4w9WgXcQ') for row in rows), content[-1500:]
        assert not any(len(row)==4 and row[1] not in ['0.0000','1.0000','clicks'] for row in rows), rows[-10:]
        report['foreground_unchanged'] = user.GetForegroundWindow() == foreground
        assert report['foreground_unchanged']
        report['passed'] = True
    finally:
        if process and process.poll() is None: process.kill(); process.wait(timeout=10)
        user.SetThreadDpiAwarenessContext(previous)
        (work/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS: current six-slot native cards ignore an empty slot, dispatch the original URL once and receive scrolling; desktop input/focus unchanged.')


if __name__ == '__main__': main()
