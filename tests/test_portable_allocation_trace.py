import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.portable_allocation_trace import reference_identity, run, trace_checks
from tools.portable_corpus_replay import SETTINGS


class AllocationTraceTests(unittest.TestCase):
    def timing(self):
        return dict(timing_diagnostic_only=True, cpp_allocations=3,
                    allocation_trace=dict(events=3, dropped=0, capacity=64,
                                          callsites=[dict(return_address='0x412345', count=3, bytes=96)]))

    def test_incomplete_trace_cannot_establish_caller_accounting(self):
        timing = self.timing()
        self.assertTrue(all(trace_checks(timing).values()))
        changed = copy.deepcopy(timing)
        changed['cpp_allocations'] = 4
        self.assertFalse(trace_checks(changed)['counter_accounting'])
        changed = copy.deepcopy(timing)
        changed['allocation_trace']['dropped'] = 1
        changed['allocation_trace']['callsites'][0]['count'] = 2
        self.assertTrue(trace_checks(changed)['counter_accounting'])
        self.assertFalse(trace_checks(changed)['all_callsites_retained'])
        changed = copy.deepcopy(timing)
        changed['allocation_trace']['callsites'] *= 2
        with self.assertRaises(ValueError):
            trace_checks(changed)
        with self.assertRaises(ValueError):
            trace_checks({})

    def test_zero_events_is_not_a_reproduced_allocation_failure(self):
        timing = self.timing()
        timing['cpp_allocations'] = timing['allocation_trace']['events'] = 0
        timing['allocation_trace']['callsites'] = []
        self.assertFalse(trace_checks(timing)['allocation_reproduced'])

    def test_same_aggregate_does_not_replace_full_reference_identity(self):
        reference = dict(tsv_sha256='reference', output={'matched': 1},
                         exact_matches_by_string_count={'3': {'matched': 1}})
        self.assertTrue(reference_identity(reference, reference, 'reference'))
        self.assertFalse(reference_identity(reference, reference, 'different-labels'))
        changed = dict(reference, exact_matches_by_string_count={'2': {'matched': 1}})
        self.assertFalse(reference_identity(reference, changed, 'reference'))

    def test_native_failure_preserves_final_report_and_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, reference, output = root / 'manifest.json', root / 'reference.json', root / 'output'
            manifest.write_text('{"source":{"provider":"github-actions"}}')
            reference.write_text(json.dumps(dict(settings=SETTINGS, source={}, datasets={
                'physical-long': {'runs': {'off-32': {'tsv_sha256': 'retained'}}}})))

            def fail(command, **kwargs):
                self.assertNotIn('--diagnostic-native-partial-cues', command)
                kwargs['stderr'].write('replay failed\n')
                raise subprocess.CalledProcessError(1, command)

            with patch('tools.portable_allocation_trace.verify_inputs'), \
                 patch('tools.portable_allocation_trace.digest', return_value='hash'), \
                 patch('tools.portable_allocation_trace.subprocess.run', side_effect=fail) as execute:
                with self.assertRaises(subprocess.CalledProcessError):
                    run(root / 'binary', root, manifest, reference, output, 10)
            self.assertEqual(execute.call_count, 1)
            report = json.loads((output / 'report.json').read_text())
            self.assertTrue(report['final'])
            self.assertEqual(report['state'], 'failed')
            self.assertFalse(report['promotion_accepted'])
            self.assertEqual((output / 'replay.stderr').read_text(), 'replay failed\n')


if __name__ == '__main__':
    unittest.main()
