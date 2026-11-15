"""Output-only retention must preserve inference, false durations and onsets."""
from pathlib import Path
import tempfile

from tests import test_portable_pending_string_trial as contracts
from tests.test_portable_evidence_retention_trial import replay_text
from tools import portable_pending_midi_retention_trial as trial


class PortablePendingMidiRetentionTrialTests(contracts.PortablePendingStringTrialTests):
    runner = trial
    trial_stem = 'midi-retention-on'
    preserve_inference = True

    def test_changed_event_fingerprint_allows_identical_inference(self):
        after = replay_text(target=1).replace('0123456789abcdef', 'fedcba9876543210')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report, _ = self.execute(root, after=after)
            self.assertTrue(report['full_recording_screen_pass'])
            self.assertTrue(report['inference_preserved'])
            self.assertTrue(report['raw_output_no_regression'])
            self.assertEqual(len(list((root / 'output').glob('*/outcome.tsv.gz'))), 3)
            self.assertFalse(list((root / 'output').glob('*/outcome.tsv')))

    def test_changed_outcome_rejects_unchanged_scores(self):
        with tempfile.TemporaryDirectory() as temp:
            report, _ = self.execute(Path(temp), drift=('outcome', 2))
            self.assertTrue(report['inference_identity']['scored_output_identical'])
            self.assertFalse(report['inference_identity']['full_outcome_bit_identical'])
            self.assertFalse(report['full_recording_screen_pass'])

    def test_even_improved_snapshot_scores_violate_output_only_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            report, _ = self.execute(Path(temp), after=replay_text(target=2))
            self.assertTrue(report['comparisons']['current-on']['gate_pass'])
            self.assertFalse(report['inference_preserved'])
            self.assertFalse(report['full_recording_screen_pass'])

    def test_incomplete_outcome_cannot_pass_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'Incomplete full outcome'):
                self.execute(Path(temp), drift=('incomplete-outcome', 2))

    def test_raw_false_duration_growth_rejects_identical_snapshot_scores(self):
        events = ((0, 'on', 43), (16, 'off', 43), *contracts.BETTER_EVENTS)
        with tempfile.TemporaryDirectory() as temp:
            report, _ = self.execute(Path(temp), events=events)
            self.assertTrue(report['held_label_improved'])
            self.assertTrue(report['inference_preserved'])
            self.assertEqual(report['raw_output_safety_delta']['false_wrong_note_voice_samples'], 16)
            self.assertFalse(report['raw_output_no_regression'])
            self.assertFalse(report['full_recording_screen_pass'])

    def test_extra_false_onset_rejects_equal_false_duration(self):
        baseline = ((0, 'on', 43), (16, 'off', 43), *contracts.BASE_EVENTS)
        events = ((0, 'on', 43), (8, 'off', 43), (8, 'on', 43),
                  (16, 'off', 43), *contracts.BETTER_EVENTS)
        with tempfile.TemporaryDirectory() as temp:
            report, _ = self.execute(Path(temp), events=events, baseline_events=baseline)
            self.assertTrue(report['held_label_improved'])
            self.assertTrue(report['inference_preserved'])
            self.assertEqual(report['raw_output_safety_delta']['false_wrong_note_voice_samples'], 0)
            self.assertEqual(report['raw_output_safety_delta']['false_wrong_note_onsets'], 1)
            self.assertFalse(report['raw_output_no_regression'])
            self.assertFalse(report['full_recording_screen_pass'])
