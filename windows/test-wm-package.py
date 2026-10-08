"""Exercise the real package supervisor with an isolated, never-opened scene."""
import argparse
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('engine', 'wm', 'wm-host', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    package = root / 'Package ñ 海'
    for folder in ('bin', 'app', 'windows', 'logs'):
        (package / folder).mkdir(parents=True)
    for source, name in ((args.engine, 'pleamar.exe'), (args.wm, 'pleamar-wm.exe'), (args.wm_host, 'pleamar-wm-host.exe')):
        shutil.copy2(source.resolve(strict=True), package / 'bin' / name)
    shutil.copy2(Path(__file__).with_name('run-desktop.ps1'), package / 'windows/run-desktop.ps1')
    (package / 'app/marea-desktop.plm').write_text('''scene Supervisor {
 fact shown = false
 surface { kind: window; size: 40, 40; keyboard: none; screens: "__wm_package_absent__"; open: shown }
 fact ready = false
}
''', encoding='utf-8')
    (package / 'app/marea-desktop.luau').write_text('fact.ready = true\n', encoding='utf-8')
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
    kernel.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
    kernel.CloseHandle.argtypes = [W.HANDLE]

    def own_handle(pid, filename):
        handle = kernel.OpenProcess(0x100000 | 0x1000 | 1, False, pid)
        assert handle, ctypes.get_last_error()
        try:
            name = ctypes.create_unicode_buffer(32768)
            size = W.DWORD(len(name))
            assert kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size))
            assert Path(name.value).resolve() == (package / 'bin' / filename).resolve()
            return handle
        except BaseException:
            kernel.CloseHandle(handle)
            raise

    report = {'passed': False, 'graphical_validation': False, 'physical_input': False, 'stages': []}
    rules = root / 'empty-session.conf'
    rules.write_text('', encoding='utf-8')
    try:
        for mode in ('normal', 'engine-killed', 'supervisor-killed'):
            namespace = 'wm-package-' + uuid.uuid4().hex
            env = dict(os.environ, PLEAMAR_CONFIG=str(root / ('config-' + mode)),
                       PLEAMAR_WM_CONFIG=str(rules),
                       PLEAMAR_SOCKET_DIR=namespace, PLEAMAR_WM_NAMESPACE=namespace, PLEAMAR_NO_RELAUNCH='1')

            def command(binary, *arguments, check=True):
                return subprocess.run([str(package / 'bin' / binary), *arguments], env=env, check=check,
                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20, creationflags=flags)

            def status():
                return json.loads(command('pleamar-wm.exe', '--say', 'wm', 'status').stdout)

            def until(check):
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    try:
                        value = check()
                        if value:
                            return value
                    except (subprocess.CalledProcessError, json.JSONDecodeError):
                        pass
                    time.sleep(.05)
                raise TimeoutError('Package supervisor did not reach the requested state')

            engine_handle = None
            with (root / (mode + '.log')).open('w', encoding='utf-8') as log:
                runner = subprocess.Popen([str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive',
                    '-ExecutionPolicy', 'Bypass', '-File', str(package / 'windows/run-desktop.ps1')],
                    env=env, stdout=log, stderr=log, creationflags=flags)
                try:
                    ready = until(lambda: status())
                    assert ready['running'] and ready['automatic_layouts'] and ready['owner']
                    assert ready.get('window_rules', 0) == 0, 'Package test inherited desktop rules'
                    assert all(not m['tiled'] for m in ready['monitors']) and ready['saved_windows'] == 0
                    engine_handle = own_handle(ready['owner'], 'pleamar.exe')
                    until(lambda: command('pleamar.exe', '--say', 'marea-desktop', 'get ready').stdout.strip() == 'true')
                    if mode == 'supervisor-killed':
                        runner.kill()
                        runner.wait(timeout=10)
                        assert status()['running'], 'Supervisor termination killed the independent recovery host'
                    if mode == 'engine-killed':
                        assert kernel.TerminateProcess(engine_handle, 97)
                    else:
                        command('pleamar.exe', '--say', 'marea-desktop', 'quit')
                    assert kernel.WaitForSingleObject(engine_handle, 15000) == 0
                    if mode != 'supervisor-killed':
                        code = runner.wait(timeout=40)
                        assert code == (97 if mode == 'engine-killed' else 0), code
                    until(lambda: command('pleamar-wm.exe', '--say', 'wm', 'status', check=False).returncode != 0)
                    journals = list((root / ('config-' + mode)).rglob('windows-session-*.json'))
                    assert len(journals) == 1 and json.loads(journals[0].read_text())['windows'] == []
                    report['stages'].append(mode)
                finally:
                    if engine_handle:
                        if kernel.WaitForSingleObject(engine_handle, 0) != 0:
                            kernel.TerminateProcess(engine_handle, 98)
                            kernel.WaitForSingleObject(engine_handle, 10000)
                        kernel.CloseHandle(engine_handle)
                    if runner.poll() is None:
                        try:
                            command('pleamar.exe', '--say', 'marea-desktop', 'quit', check=False)
                            runner.wait(timeout=35)
                        except (subprocess.SubprocessError, TimeoutError):
                            runner.kill()
                            runner.wait(timeout=10)
        assert not any('first frame' in f.read_text(encoding='utf-8', errors='replace') for f in (package / 'logs').glob('marea-*.log'))
        report['passed'] = True
    finally:
        (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
