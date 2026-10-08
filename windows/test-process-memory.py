"""Exercise real owned allocations and reject missing native memory counters."""
import ctypes as c
import os
import unittest
from process_memory import Memory, Memory2, Reader


@unittest.skipUnless(os.name == 'nt', 'Native Windows process counters')
class NativeMemoryTests(unittest.TestCase):
    def setUp(self):
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.kernel.GetCurrentProcess.restype = c.c_void_p
        self.handle = self.kernel.GetCurrentProcess()

    def test_private_commit_and_resident_pages_track_an_owned_allocation(self):
        reader = Reader()
        before = reader.read(self.handle)
        self.kernel.VirtualAlloc.argtypes = [c.c_void_p, c.c_size_t, c.c_uint32, c.c_uint32]
        self.kernel.VirtualAlloc.restype = c.c_void_p
        self.kernel.VirtualFree.argtypes = [c.c_void_p, c.c_size_t, c.c_uint32]
        self.kernel.VirtualFree.restype = c.c_int32
        size = 16 * 1024 * 1024
        address = self.kernel.VirtualAlloc(None, size, 0x3000, 4)
        self.assertTrue(address)
        try:
            c.memset(address, 0x5a, size)
            during = reader.read(self.handle)
            self.assertGreaterEqual(during['private_commit_mib'] - before['private_commit_mib'], 15)
            self.assertEqual(during['private_mib'], during['private_commit_mib'])
            self.assertGreater(during['working_set_mib'], 0)
            if during['private_working_set_mib'] is not None:
                self.assertGreater(during['private_working_set_mib'], 0)
                self.assertLessEqual(during['private_working_set_mib'], during['working_set_mib'])
                self.assertGreaterEqual(during['shared_commit_mib'], 0)
            else:
                self.assertIsNone(during['shared_commit_mib'])
            print('Owned allocation counters:', during)
        finally:
            self.assertTrue(self.kernel.VirtualFree(address, 0, 0x8000))
        after = reader.read(self.handle)
        self.assertGreaterEqual(during['private_commit_mib'] - after['private_commit_mib'], 15)

    def test_invalid_handle_is_an_error_not_a_zero_sample(self):
        with self.assertRaises(OSError):
            Reader().read(None)

    def test_old_kernel_prefix_does_not_turn_unwritten_fields_into_zero(self):
        reader = Reader()
        def prefix_only(handle, pointer, length):
            memory = c.cast(pointer, c.POINTER(Memory)).contents
            memory.working = 8 * 2**20
            memory.private = 3 * 2**20
            return True
        reader.query = prefix_only
        for _ in range(2):
            sample = reader.read(self.handle)
            self.assertEqual(sample['private_commit_mib'], 3)
            self.assertIsNone(sample['private_working_set_mib'])
            self.assertIsNone(sample['shared_commit_mib'])
            self.assertEqual(sample['memory_counter_format'], 'PROCESS_MEMORY_COUNTERS_EX')

    def test_rejected_extended_buffer_retries_the_supported_prefix(self):
        for error in (87, 122):
            with self.subTest(error=error):
                reader = Reader()
                lengths = []
                def old_kernel(handle, pointer, length):
                    lengths.append(length)
                    if length == c.sizeof(Memory2):
                        c.set_last_error(error)
                        return False
                    memory = c.cast(pointer, c.POINTER(Memory)).contents
                    memory.working = 8 * 2**20
                    memory.private = 3 * 2**20
                    return True
                reader.query = old_kernel
                for _ in range(2):
                    sample = reader.read(self.handle)
                    self.assertEqual(sample['private_commit_mib'], 3)
                    self.assertIsNone(sample['private_working_set_mib'])
                self.assertEqual(lengths, [c.sizeof(Memory2), c.sizeof(Memory), c.sizeof(Memory)])

    def test_access_denied_does_not_retry_or_mask_the_failure(self):
        reader = Reader()
        calls = []
        def denied(handle, pointer, length):
            calls.append(length)
            c.set_last_error(5)
            return False
        reader.query = denied
        with self.assertRaises(OSError) as failure:
            reader.read(self.handle)
        self.assertEqual(failure.exception.winerror, 5)
        self.assertEqual(calls, [c.sizeof(Memory2)])


class LayoutTests(unittest.TestCase):
    def test_native_counter_prefix_has_fixed_width_fields(self):
        self.assertEqual(Memory.working.offset, 8 + c.sizeof(c.c_size_t))
        self.assertEqual(Memory2.private_working.offset, c.sizeof(Memory))
        self.assertEqual(Memory2.shared_commit.offset, c.sizeof(Memory) + c.sizeof(c.c_size_t))


if __name__ == '__main__':
    unittest.main()
