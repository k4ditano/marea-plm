"""Check native resource intervals without creating a window or sampling other apps."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from profile_resources import Probe, summarize


class Intervals(unittest.TestCase):
    def sample(self, elapsed=0, cpu=1, private=30, shared=None):
        return dict(label='owned', elapsed=elapsed, cpu_seconds=cpu, working_set_mib=50,
                    private_commit_mib=private, private_working_set_mib=shared,
                    shared_commit_mib=None, handles=20, gdi_objects=0, user_objects=0)

    def test_cpu_uses_one_core_and_retains_unknown_resident_counters(self):
        result = summarize(self.sample(), self.sample(elapsed=4, cpu=3, private=25))
        self.assertEqual(result['cpu_one_core_percent'], 50)
        self.assertEqual(result['change']['private_commit_mib'], -5)
        self.assertIsNone(result['change']['private_working_set_mib'])
        self.assertIsNone(result['change']['shared_commit_mib'])
        self.assertEqual(result['change']['gdi_objects'], 0)

    def test_available_resident_counters_are_separate_from_commit(self):
        result = summarize(self.sample(shared=10), self.sample(elapsed=2, cpu=4, shared=15))
        self.assertEqual(result['cpu_one_core_percent'], 150)
        self.assertEqual(result['change']['private_commit_mib'], 0)
        self.assertEqual(result['change']['private_working_set_mib'], 5)

    def test_invalid_intervals_do_not_become_zero_usage(self):
        for after in (self.sample(), self.sample(elapsed=-1), self.sample(elapsed=1, cpu=0)):
            with self.assertRaises(ValueError):
                summarize(self.sample(), after)


@unittest.skipUnless(os.name == 'nt', 'Native owned-process counters require Windows')
class NativeProbe(unittest.TestCase):
    def test_owned_child_is_measured_and_its_exit_is_not_reported_as_zero(self):
        parent = Path.cwd().resolve()
        with tempfile.TemporaryDirectory(prefix='owned-resource-', dir=parent) as temporary:
            folder = Path(temporary).resolve()
            self.assertEqual(folder.parent, parent)
            # A message-only window initializes USER counters without appearing
            # on a display or participating in focus or keyboard dispatch.
            child = '''import ctypes as c,time
from ctypes import wintypes as w
user=c.WinDLL('user32',use_last_error=True)
user.CreateWindowExW.argtypes=[w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,w.HWND,w.HMENU,w.HINSTANCE,w.LPVOID]
user.CreateWindowExW.restype=w.HWND
window=user.CreateWindowExW(0,'STATIC','owned counters',0,0,0,0,0,w.HWND(-3),None,None,None)
assert window,c.get_last_error()
print('ready',flush=True)
time.sleep(20)
'''
            process = subprocess.Popen([sys.executable, '-c', child], stdout=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            try:
                self.assertEqual(process.stdout.readline().strip(), 'ready')
                probe = Probe(process, folder / 'resources.json')
                interval = probe.observe('owned-child', .05)
                self.assertGreater(interval['seconds'], 0)
                self.assertGreater(interval['final']['working_set_mib'], 0)
                self.assertGreater(interval['final']['handles'], 0)
                probe.finish()
                report = json.loads(probe.output.read_text(encoding='utf-8'))
                self.assertEqual(report['process_id'], process.pid)
                self.assertTrue(report['complete'])
                self.assertFalse(report['gpu_memory_measured'])
            finally:
                process.kill()
                process.wait(timeout=10)
                process.stdout.close()
            with self.assertRaisesRegex(RuntimeError, 'exited'):
                probe.sample('after-exit')


if __name__ == '__main__':
    unittest.main()
