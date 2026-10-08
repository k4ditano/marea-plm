"""Process counters for the owned native renderer fixture, not a GPU benchmark."""
import ctypes as c
from ctypes import wintypes as w
import json
import time
from process_memory import Reader


class Probe:
    def __init__(self, process, output):
        self.process, self.output = process, output
        self.memory = Reader()
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.user = c.WinDLL('user32', use_last_error=True)
        self.kernel.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = w.BOOL
        self.kernel.GetProcessHandleCount.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
        self.kernel.GetProcessHandleCount.restype = w.BOOL
        self.user.GetGuiResources.argtypes = [w.HANDLE, w.DWORD]
        self.user.GetGuiResources.restype = w.DWORD
        self.began = time.monotonic()
        self.report = dict(process_id=process.pid, scope='native renderer with isolated fixture logic',
                           sdk=False, device_services=False, gpu_memory_measured=False,
                           physical_display_fps=False, samples=[], intervals=[], complete=False)

    def save(self):
        self.output.write_text(json.dumps(self.report, indent=2) + '\n', encoding='utf-8')

    def sample(self, label):
        if self.process.poll() is not None:
            raise RuntimeError('Owned renderer exited during resource measurement')
        handle = int(self.process._handle)
        created, exited, system, user = [w.FILETIME() for _ in range(4)]
        handles = w.DWORD()
        for function, args in ((self.kernel.GetProcessTimes, (handle, c.byref(created), c.byref(exited), c.byref(system), c.byref(user))),
                               (self.kernel.GetProcessHandleCount, (handle, c.byref(handles)))):
            if not function(*args):
                raise c.WinError(c.get_last_error())
        cpu = sum((value.dwHighDateTime << 32) | value.dwLowDateTime for value in (system, user)) / 1e7
        gui = {}
        for flag, name in ((0, 'gdi_objects'), (1, 'user_objects')):
            c.set_last_error(0)
            count = self.user.GetGuiResources(handle, flag)
            if count == 0 and c.get_last_error():
                raise c.WinError(c.get_last_error())
            gui[name] = count
        value = dict(label=label, elapsed=time.monotonic() - self.began, cpu_seconds=cpu,
                     handles=handles.value, **self.memory.read(handle), **gui)
        self.report['samples'].append(value)
        self.save()
        return value

    def observe(self, label, seconds):
        if seconds <= 0:
            raise ValueError('Resource observation must have a positive duration')
        before = self.sample(label)
        after = before
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(1, remaining))
            after = self.sample(label)
        interval = summarize(before, after)
        self.report['intervals'].append(interval)
        self.save()
        return interval

    def finish(self):
        self.report['complete'] = True
        self.save()


def summarize(before, after):
    elapsed = after['elapsed'] - before['elapsed']
    cpu = after['cpu_seconds'] - before['cpu_seconds']
    if elapsed <= 0 or cpu < 0:
        raise ValueError('Resource samples need increasing time and a nondecreasing process CPU counter')
    changes = {}
    for name in ('working_set_mib', 'private_commit_mib', 'private_working_set_mib',
                 'shared_commit_mib', 'handles', 'gdi_objects', 'user_objects'):
        changes[name] = None if before[name] is None or after[name] is None else round(after[name] - before[name], 3)
    return dict(label=before['label'], seconds=round(elapsed, 3),
                cpu_one_core_percent=round(100 * cpu / elapsed, 3),
                initial=before, final=after, change=changes)
