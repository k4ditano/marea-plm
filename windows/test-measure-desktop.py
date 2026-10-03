"""Reject contaminated performance samples even when both endpoint checks agree."""
from pathlib import Path
import runpy
import unittest

summarize = runpy.run_path(str(Path(__file__).with_name('measure-desktop.py')))['summarize_trace']


class TraceTests(unittest.TestCase):
    def test_open_close_between_identical_endpoints_is_not_a_closed_sample(self):
        intervals, trace = summarize(['0.0\t0.0000\t2.0000', '16.7\t1.0000\t2.0000',
                                      '33.4\t0.0000\t2.0000'], 'false', 'classic')
        self.assertEqual(intervals['mean_ms'], 16.7)
        self.assertEqual(trace['mismatches'], 1)
        self.assertEqual(trace['first_mismatches'], [(16.7, 1.0, 2.0)])

    def test_skin_change_invalidates_an_open_sample(self):
        _, trace = summarize(['10.0\t1.0000\t0.0000', '27.0\t1.0000\t1.0000'], 'true', 'lens')
        self.assertEqual(trace['mismatches'], 1)

    def test_valid_trace_ignores_diagnostics_and_partial_buffer_edges(self):
        intervals, trace = summarize(['0\t2.0000', '15.0\t0.0000\t1.0000', 'cycle diagnostic',
                                      '32.0\t0.0000\t1.0000', '50.0\t'], 'false', 'liquid')
        self.assertEqual(intervals['count'], 1)
        self.assertEqual(intervals['max_ms'], 17)
        self.assertEqual(trace['samples'], 2)
        self.assertEqual(trace['mismatches'], 0)

    def test_missing_trace_is_not_a_pass(self):
        with self.assertRaisesRegex(RuntimeError, 'No native update samples'):
            summarize(['cycle diagnostic'], 'false', 'classic')


if __name__ == '__main__':
    unittest.main()
