"""Read committed and resident memory separately; old Windows reports unknowns.

PROCESS_MEMORY_COUNTERS_EX2 requires the September 2023 Windows 10/11 updates:
https://learn.microsoft.com/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex2
These process counters are not unique physical RAM or GPU memory totals.
"""
import ctypes as c
import os


class Memory(c.Structure):
    _fields_ = [('cb', c.c_uint32), ('faults', c.c_uint32)] + [
        (name, c.c_size_t) for name in ('peak_working', 'working', 'peak_paged',
        'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]


class Memory2(c.Structure):
    _fields_ = Memory._fields_ + [('private_working', c.c_size_t), ('shared_commit', c.c_uint64)]


class Reader:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('Process memory counters require native Windows')
        self.dll = c.WinDLL('psapi', use_last_error=True)
        self.query = self.dll.GetProcessMemoryInfo
        self.query.argtypes = [c.c_void_p, c.c_void_p, c.c_uint32]
        self.query.restype = c.c_int32
        self.extended = True

    def read(self, handle):
        memory = Memory2() if self.extended else Memory()
        memory.cb = c.sizeof(memory)
        if self.extended:
            memory.private_working = c.c_size_t(-1).value
            memory.shared_commit = c.c_uint64(-1).value
        ok = self.query(handle, c.byref(memory), memory.cb)
        if not ok:
            error = c.get_last_error()
            # Older kernels can reject the larger structure. Access failures
            # are not a reason to substitute zero or a previous sample.
            if not self.extended or error not in (87, 122):
                raise c.WinError(error)
            self.extended = False
            return self.read(handle)
        extended = self.extended and memory.private_working != c.c_size_t(-1).value \
            and memory.shared_commit != c.c_uint64(-1).value
        # Some older kernels accept a larger buffer but fill only EX's prefix.
        if self.extended and not extended:
            self.extended = False
        mib = lambda value: round(value / 2**20, 3)
        return dict(working_set_mib=mib(memory.working), private_mib=mib(memory.private),
                    private_commit_mib=mib(memory.private),
                    private_working_set_mib=mib(memory.private_working) if extended else None,
                    shared_commit_mib=mib(memory.shared_commit) if extended else None,
                    memory_counter_format='PROCESS_MEMORY_COUNTERS_EX2' if extended else 'PROCESS_MEMORY_COUNTERS_EX')
