"""Synthetic contracts for the frozen relief screen; no audio or native execution."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.portable_calibrated_midi_retention_corpus import relief_counters, relief_gate, run


class ReliefScreenTests(unittest.TestCase):
    def test_counter_partition_and_disagreement(self):
        line = ('m3_replay: upper_fretted_relief evaluated=10 no_parent=2 '
                'related_blocked=3 applied=5 rendered_disagreements=3 active_only=2 rendered_only=1')
        self.assertEqual(relief_counters(line)['applied'], 5)
        for bad in ('', line + '\n' + line, line.replace('evaluated=10', 'evaluated=11'),
                    line.replace('rendered_disagreements=3', 'rendered_disagreements=4')):
            with self.assertRaises(ValueError):
                relief_counters(bad)

    def test_usefulness_is_lane_matches_and_attacks_are_independent(self):
        before = {'labels': [{'midi_note': 60, 'matched': 0}, {'midi_note': 65, 'matched': 10}]}
        after = {'labels': [{'midi_note': 60, 'matched': 9000}, {'midi_note': 65, 'matched': 5009}]}
        comparison = {'changed_held_labels': []}
        self.assertFalse(relief_gate(comparison, before, after)['usefulness_pass'])
        after['labels'][1]['matched'] = 5010
        comparison['changed_held_labels'] = [{'note_on_delta': 1}]
        result = relief_gate(comparison, before, after)
        self.assertTrue(result['usefulness_pass'])
        self.assertFalse(result['retrigger_pass'])

    def test_local_execution_refused_before_io(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaisesRegex(RuntimeError, 'only on GitHub Actions'):
                run(*(Path('/does-not-exist') for _ in range(5)), policy='upper-fretted-relief')


if __name__ == '__main__':
    unittest.main()
