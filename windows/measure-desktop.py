"""Measure native Marea update cadence and process resources in isolated state.

Run with the normal Marea instance stopped. The test opens actual desktop panels;
keep other workloads stable and avoid clicking outside the panel while sampling.
Update intervals are not physical display FPS. No psutil or Unix shell is needed.
"""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import re
import subprocess
import sys
import time


def summarize_trace(lines, opened, skin):
    # Marea declares `skin: lens | liquid | classic`; --record writes enum indices.
    expected = (float(opened == 'true'), float(('lens', 'liquid', 'classic').index(skin)))
    rows = [tuple(map(float, match.groups())) for line in lines
            if (match := re.fullmatch(r'(\d+(?:\.\d+)?)\t([\d.]+)\t([\d.]+)', line))]
    if len(rows) < 2:
        raise RuntimeError('No native update samples')
    deltas = sorted(b[0] - a[0] for a, b in zip(rows, rows[1:]))
    mismatches = [row for row in rows if row[1:] != expected]
    return (dict(count=len(deltas), mean_ms=round(sum(deltas) / len(deltas), 2),
                 p99_ms=round(deltas[min(len(deltas)-1, int(len(deltas)*.99))], 2), max_ms=round(max(deltas), 2)),
            dict(samples=len(rows), mismatches=len(mismatches), first_mismatches=mismatches[:3]))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--scene', type=Path, default=Path(__file__).resolve().parents[1] / 'marea-desktop.plm')
    parser.add_argument('--screen', help='Confine all per-monitor surfaces to this exact output name')
    parser.add_argument('--output', required=True, type=Path, help='New directory for logs, isolated state and report')
    parser.add_argument('--seconds', type=int, default=30, help='Seconds per state, 5 to 300')
    parser.add_argument('--repeats', type=int, default=2, help='Complete Classic/Liquid/Lens cycles, 1 to 10')
    parser.add_argument('--skins', nargs='+', choices=('classic', 'liquid', 'lens'),
                        default=['classic', 'liquid', 'lens'], help='Looks to sample, in order')
    parser.add_argument('--states', nargs='+', choices=('false', 'true'), default=['false', 'true'],
                        help='Closed/open states to sample, in order')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This measures an actual Windows desktop, not headless execution')
    if not 5 <= args.seconds <= 300 or not 1 <= args.repeats <= 10:
        parser.error('seconds must be 5..300 and repeats 1..10')
    binary, scene, output = args.binary.resolve(strict=True), args.scene.resolve(strict=True), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    state = output / 'state'
    state.mkdir()
    (state / 'claude').mkdir()
    (state / 'claude/.claude.json').write_text('null', encoding='utf-8')
    (state / 'codex/sessions').mkdir(parents=True)
    env = dict(os.environ, APPDATA=str(state), PLEAMAR_SOCKET_DIR=f'marea-perf-{os.getpid()}',
               PLEAMAR_TIMING='1', PLEAMAR_NO_RELAUNCH='1', MAREA_SEARCH_HOTKEY='',
               CLAUDE_CONFIG_DIR=str(state / 'claude'), CODEX_HOME=str(state / 'codex'))

    class Memory(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    user32.GetGuiResources.restype = wintypes.DWORD
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessHandleCount.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Memory), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    def metrics(process):
        created, exited, system, user = [wintypes.FILETIME() for _ in range(4)]
        memory, handles = Memory(), wintypes.DWORD()
        memory.cb = ctypes.sizeof(memory)
        for success in (
            kernel.GetProcessTimes(int(process._handle), ctypes.byref(created), ctypes.byref(exited), ctypes.byref(system), ctypes.byref(user)),
            kernel.GetProcessHandleCount(int(process._handle), ctypes.byref(handles)),
            psapi.GetProcessMemoryInfo(int(process._handle), ctypes.byref(memory), memory.cb),
        ):
            if not success:
                raise ctypes.WinError(ctypes.get_last_error())
        cpu = sum((value.dwHighDateTime << 32) | value.dwLowDateTime for value in (system, user)) / 1e7
        gui = {}
        for flag, name in ((0, 'gdi_objects'), (1, 'user_objects')):
            ctypes.set_last_error(0)
            count = user32.GetGuiResources(int(process._handle), flag)
            if count == 0 and ctypes.get_last_error():
                raise ctypes.WinError(ctypes.get_last_error())
            gui[name] = count
        return dict(cpu_seconds=cpu, working_set_mib=round(memory.WorkingSetSize / 2**20, 2),
                    private_mib=round(memory.PrivateUsage / 2**20, 2), handles=handles.value, **gui)

    def ask(command):
        return subprocess.check_output([str(binary), '--say', scene.stem, command], env=env,
                                       stderr=subprocess.DEVNULL, encoding='utf-8', timeout=10,
                                       creationflags=subprocess.CREATE_NO_WINDOW).strip()

    log_path = output / 'native.log'
    report = dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  scene_sha256=hashlib.sha256(scene.read_bytes()).hexdigest(),
                  logical_cpus=os.cpu_count(), samples=[], complete=False,
                  skins=args.skins, states=args.states,
                  requested_screen=args.screen,
                  note='Native update intervals, not physical display FPS. Isolated preferences/quota data; existing GPU driver/cache.')
    process = None
    try:
        with log_path.open('w', encoding='utf-8') as log:
            process = subprocess.Popen([str(binary), '--scene', str(scene), '--no-hud', '--stall', '0',
                                        '--record', 'open,skin', *(['--screen', args.screen] if args.screen else [])], env=env, cwd=scene.parent,
                                       stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 45
            while True:
                content = log_path.read_text(encoding='utf-8', errors='replace')
                frame = re.search(r'first frame (\d+) ms', content)
                if frame and ask('get windows_initialized') == 'true':
                    report['first_frame_ms'] = int(frame[1])
                    report['startup'] = [line for line in content.splitlines() if 'GPU startup ms' in line]
                    report['surfaces'] = [line for line in content.splitlines() if line.startswith('render · surface')]
                    if args.screen and (not report['surfaces'] or any(' on ' + args.screen + ' ·' not in line for line in report['surfaces'])):
                        raise RuntimeError('A surface was created outside the requested output')
                    break
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Native initialization failed: ' + content)
                time.sleep(.1)
            time.sleep(5)
            for repeat in range(args.repeats):
                for skin in args.skins:
                    ask(f'fact skin {skin}')
                    for opened in args.states:
                        ask(f'fact open {opened}')
                        time.sleep(3)
                        before = metrics(process)
                        initial = [ask('get open'), ask('get skin')]
                        byte_start = log_path.stat().st_size
                        started = time.monotonic()
                        points = []
                        while time.monotonic() - started < args.seconds:
                            time.sleep(min(5, max(.01, args.seconds - (time.monotonic() - started))))
                            points.append(dict(metrics(process), elapsed_seconds=round(time.monotonic() - started, 3)))
                        elapsed = time.monotonic() - started
                        byte_end = log_path.stat().st_size
                        final = [ask('get open'), ask('get skin')]
                        with log_path.open('rb') as recorded:
                            recorded.seek(byte_start)
                            lines = recorded.read(byte_end - byte_start).decode('utf-8', errors='replace').splitlines()
                        intervals, trace = summarize_trace(lines, opened, skin)
                        # Trace output is buffered. Each three-second settling interval
                        # keeps a prior state's tail out of the measured byte range.
                        sample = dict(repeat=repeat, skin=skin, opened=opened, seconds=round(elapsed, 3),
                                      cpu_one_core_percent=round(100 * (points[-1]['cpu_seconds'] - before['cpu_seconds']) / elapsed, 2),
                                      before=before, after=points[-1], resources=points,
                                      update_intervals=intervals, state_trace=trace, initial=initial, final=final,
                                      state_valid=initial == [opened, skin] and final == initial and trace['mismatches'] == 0)
                        sample['cpu_machine_percent'] = round(sample['cpu_one_core_percent'] / os.cpu_count(), 2)
                        report['samples'].append(sample)
                        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                        if not sample['state_valid']:
                            raise RuntimeError(f'Panel state changed during sample: {initial} -> {final}; '
                                               f"{trace['mismatches']} trace samples disagree with the requested state")
                        print(json.dumps({key: sample[key] for key in ('repeat', 'skin', 'opened', 'cpu_machine_percent', 'update_intervals')}, ensure_ascii=True), flush=True)
            report['complete'] = True
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        if process is not None and process.poll() is None:
            try:
                ask('quit')
                process.wait(timeout=15)
            except Exception as error:
                report['complete'] = False
                report['shutdown_error'] = str(error)
                process.kill()
                process.wait(timeout=10)
        if process is not None:
            report['exit_code'] = process.returncode
        if log_path.exists():
            content = log_path.read_text(encoding='utf-8', errors='replace')
            report['runtime_errors'] = [line for line in content.splitlines() if 'runtime error:' in line or 'panicked at' in line]
        if report.get('exit_code') != 0 or report.get('runtime_errors'):
            report['complete'] = False
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if report.get('exit_code') != 0 or report['runtime_errors'] or report.get('shutdown_error'):
        raise RuntimeError('Native runtime failed; see report.json and native.log')
    print(f'Report: {output / "report.json"}', flush=True)


if __name__ == '__main__':
    main()
