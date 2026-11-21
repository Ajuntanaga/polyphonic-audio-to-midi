"""Synthetic report/clock checks only; native and recorded execution stays on GHA."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.portable_basic_pitch_native import (NATIVE, array_comparison, delivered_events,
    distribution, run, sequence, table, timing_report)


class NativeReportTests(unittest.TestCase):
    def test_delivery_never_backdates_worker_or_reorders(self):
        rows=[dict(frame=1,note=60,on=1,source_end=640,ready_ns=7_000_000,
                   emitted_ns=8_000_000,cleanup=0),
              dict(frame=0,note=60,on=0,source_end=1280,ready_ns=14_000_000,
                   emitted_ns=14_000_001,cleanup=1)]
        events=delivered_events(rows)
        self.assertEqual(events[0]['available_ns'],6_666_667)
        self.assertEqual([r['kind'] for r in events],['on','off'])
        self.assertEqual(events[1]['emitted_ns'],14_000_001)
        with self.assertRaises(ValueError):
            delivered_events([dict(rows[0],emitted_ns=6_999_999)])
        with self.assertRaises(ValueError):
            delivered_events([rows[0],dict(rows[1],ready_ns=0,emitted_ns=1)])

    def test_callback_allocations_or_one_deadline_overrun_fail(self):
        callbacks=[dict(duration_ns=100,late_ns=0,allocations=0,frees=0)]*100
        workers=[dict(called=1,service_ns=10_000_000,queued_ns=100,model_ns=9_000_000)]
        self.assertTrue(all(timing_report(callbacks,workers)['gates'].values()))
        allocated=[dict(callbacks[0],allocations=1,frees=1)]+callbacks[1:]
        gates=timing_report(allocated,workers)['gates']
        self.assertFalse(gates['callback_zero_allocations'])
        self.assertFalse(gates['callback_zero_deallocations'])
        delayed=[dict(callbacks[0],duration_ns=NATIVE['callback_max_limit_ns']+1)]+callbacks[1:]
        gates=timing_report(delayed,workers)['gates']
        self.assertTrue(gates['callback_p99'])
        self.assertFalse(gates['callback_max'])
        self.assertFalse(gates['callback_zero_overruns'])
        backlog=[dict(workers[0],queued_ns=NATIVE['backlog_max_limit_ns']+1)]
        self.assertFalse(timing_report(callbacks,backlog)['gates']['worker_maximum_backlog'])

    def test_arrays_report_drift_or_nonfinite(self):
        import numpy as np
        source=np.array([1.,2.],dtype=np.float32)
        self.assertTrue(array_comparison(source,source,1e-5)['bit_identical'])
        self.assertFalse(array_comparison(source,source+.1,1e-5)['pass_'])
        self.assertFalse(array_comparison(source,source[:1],1e-5)['pass_'])
        self.assertFalse(array_comparison(source,np.array([1.,float('nan')]),1e-5)['pass_'])

    def test_schema_and_nonempty_timing(self):
        self.assertEqual(distribution(range(1,101))['p99'],99)
        with self.assertRaises(ValueError): distribution([])
        with self.assertRaises(ValueError): distribution([-1])
        with self.assertRaises(ValueError): sequence([dict(on=2,note=60,frame=1)])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.tsv'
            path.write_text('first\tsecond\n1\t2\n')
            self.assertEqual(table(path,['first','second']),[dict(first=1,second=2)])
            with self.assertRaises(ValueError): table(path,['second','first'])

    def test_local_driver_rejected_before_file_access(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
            with self.assertRaises(RuntimeError):
                run(*[Path('/must-not-open')]*5)


if __name__=='__main__':
    unittest.main()
