import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_portable_pending_string_trace as shared
from tools import portable_forced_pending_string_trace as trace
from tools.portable_forced_pending_string_trial import FLAG


class PortableForcedPendingStringTraceTests(unittest.TestCase):
    def execute(self, root, *, drift=None):
        helper = shared.PortablePendingStringTraceTests()
        args, text = helper.fixture(root)
        references = json.loads(args[3].read_text())
        policies = references['replay_references']
        policies['forced-trial-on'] = policies.pop('trial-on')
        args[3].write_text(json.dumps(references))
        with patch.object(trace, 'CASES', shared.CASES), patch.object(
                trace, 'window_for', return_value=(0, 192)):
            mocked = helper.execute(args, text, drift=drift, runner=trace.run, trial_flag=FLAG)
        return args, mocked

    def test_six_captures_use_forced_policy_and_preserve_saved_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            args, mocked = self.execute(Path(directory))
            self.assertEqual(mocked.call_count, 6)
            for index, call in enumerate(mocked.call_args_list):
                command = call.args[0]
                self.assertEqual(FLAG in command, index >= 3)
                self.assertNotIn('--diagnostic-pending-string-reservation', command)
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertEqual(report['schema'], 'm3_forced_pending_string_reservation_trace_v1')
            self.assertEqual(report['state'], 'completed')
            self.assertTrue(report['saved_references_bit_identical'])
            self.assertTrue(report['repeated_policy_streams_bit_identical'])
            self.assertEqual({row['policy'] for row in report['runs'].values()},
                             {'current-on', 'forced-trial-on'})
            self.assertFalse(report['runtime_rule_changed'])
            self.assertFalse(report['promotion_accepted'])

    def test_changed_midi_or_repeated_outcome_is_rejected(self):
        for drift, message in (('midi', 'saved output or raw MIDI'),
                               ('outcome', 'complete MIDI or outcome')):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, message):
                    self.execute(Path(directory), drift=drift)

    def test_windows_include_one_second_of_history_and_complete_label(self):
        for label in trace.CASES:
            start, end = trace.window_for(label)
            self.assertGreaterEqual(label['start_sample'] - start, 96000)
            self.assertLess(label['start_sample'] - start, 96064)
            self.assertGreater(end, label['end_sample'])
            self.assertEqual(start % 64, 0)
            self.assertEqual(end % 64, 0)
        self.assertEqual(trace.window_for(dict(start_sample=20, end_sample=100))[0], 0)


if __name__ == '__main__':
    unittest.main()
