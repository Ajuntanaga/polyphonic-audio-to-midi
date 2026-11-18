import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from tools import portable_ordinary_harmonic_admission as t


class LocalOnsetAssignmentTraceTests(unittest.TestCase):
    def exercise(self, drift=False, sustain=False):
        flag = "--diagnostic-supported-sustain-renewal" if sustain else "--diagnostic-local-onset-evidence"
        start, end = (58.6, 59.5) if sustain else (47.5, 48.5)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            conditions = [(t.OFF, []), (t.CURRENT, [t.COLLISION]),
                          (t.TRIAL, [t.COLLISION, flag])]
            commands = []
            def native(command, **kwargs):
                commands.append(command)
                Path(command[command.index('--midi-event-trace') + 1]).write_bytes(b'events')
                Path(command[command.index('--assignment-trace') + 1]).write_text('costs')
            runs = {mode: {'midi_trace_sha256': hashlib.sha256(b'events').hexdigest()}
                    for mode in (t.CURRENT, t.TRIAL)}
            if drift:
                runs[t.TRIAL]['midi_trace_sha256'] = 'different'
            with (patch.object(t.subprocess, 'run', side_effect=native),
                  patch.object(t, 'read_replay', return_value={}),
                  patch.object(t, 'compare_replays', return_value={
                      'output_bit_identical': True, 'changed_labels': []}),
                  patch.object(t, 'compress_trace_window', return_value={'verified': True})):
                result = t.trace_local_onset_assignments(root/'binary', root, root,
                    conditions, {t.CURRENT: {}, t.TRIAL: {}}, runs, time.monotonic()+10, start=start, end=end)
            self.assertEqual(set(result), {t.CURRENT, t.TRIAL})
            self.assertEqual(len(commands), 2)
            self.assertNotIn(flag, commands[0])
            self.assertIn(flag, commands[1])
            for command in commands:
                self.assertEqual(command[command.index('--assignment-trace-start')+1], str(start))
                self.assertEqual(command[command.index('--assignment-trace-end')+1], str(end))
                self.assertNotIn('--candidate-rescue-harmonic-cues', command)

    def test_both_policies_are_observed_without_rescue_flags(self):
        self.exercise()

    def test_midi_drift_rejects_observation(self):
        with self.assertRaisesRegex(ValueError, 'tracing changed output'):
            self.exercise(drift=True)

    def test_sustain_loss_window_preserves_policy_and_bounds(self):
        self.exercise(sustain=True)
