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

    @staticmethod
    def lifecycle(*, attacks=0, repeats=0, longest=0):
        return dict(coverage_valid=True, labels=[dict(label_index=0, midi_note=65,
            string_mask=1, start_sample=0, end_sample=100,
            note_ons_inside_label=attacks, retrigger_note_ons_inside_label=repeats,
            longest_exact_hold_samples=longest)])

    def test_usefulness_is_lane_matches_and_retriggers_are_independent(self):
        before = {'labels': [{'midi_note': 60, 'matched': 0}, {'midi_note': 65, 'matched': 10}]}
        after = {'labels': [{'midi_note': 60, 'matched': 9000}, {'midi_note': 65, 'matched': 5009}]}
        current = self.lifecycle()
        trial = self.lifecycle(attacks=1, longest=100)
        self.assertFalse(relief_gate(before, after, current, trial)['usefulness_pass'])
        after['labels'][1]['matched'] = 5010
        result = relief_gate(before, after, current, trial)
        self.assertTrue(result['usefulness_pass'])
        self.assertTrue(result['retrigger_pass'])
        trial['labels'][0].update(note_ons_inside_label=2, retrigger_note_ons_inside_label=1)
        result = relief_gate(before, after, current, trial)
        self.assertFalse(result['retrigger_pass'])

    def test_same_total_attacks_can_hide_a_retrigger_regression(self):
        replay = {'labels': []}
        current = self.lifecycle(attacks=2, repeats=0, longest=80)
        trial = self.lifecycle(attacks=2, repeats=1, longest=80)
        result = relief_gate(replay, replay, current, trial)
        self.assertFalse(result['retrigger_pass'])
        self.assertEqual(result['retrigger_regressions'][0]['retrigger_delta'], 1)
        self.assertTrue(result['longest_hold_pass'])
        trial['labels'][0]['longest_exact_hold_samples'] = 79
        self.assertFalse(relief_gate(replay, replay, current, trial)['longest_hold_pass'])

    def test_invalid_pairing_cannot_pass_retrigger_or_longest_hold_gate(self):
        invalid = dict(coverage_valid=False, labels=None)
        result = relief_gate({'labels': []}, {'labels': []}, self.lifecycle(), invalid)
        self.assertFalse(result['retrigger_pass'])
        self.assertFalse(result['longest_hold_pass'])

    def test_local_execution_refused_before_io(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaisesRegex(RuntimeError, 'only on GitHub Actions'):
                run(*(Path('/does-not-exist') for _ in range(5)), policy='upper-fretted-relief')


if __name__ == '__main__':
    unittest.main()
