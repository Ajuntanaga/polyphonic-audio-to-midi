import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_portable_evidence_retention_trial as fixtures
from tests.test_portable_evidence_retention_trial import replay_text
from tools import portable_pending_string_trial as trial
from tools.portable_assignment_trace import digest


LABEL = dict(label_index=55, midi_note=42, string_mask=1, start_sample=0, end_sample=192)
BASE_EVENTS = ((64, 'on', 42), (128, 'off', 42), (160, 'on', 42), (176, 'off', 42))
BETTER_EVENTS = ((32, 'on', 42), (191, 'off', 42))


def midi_text(events):
    stream = io.StringIO()
    stream.write('# m3_midi_events_v1\n')
    writer = csv.DictWriter(stream, fieldnames=(
        'sample', 'kind', 'note', 'velocity', 'voice_id', 'sequence'), delimiter='\t')
    writer.writeheader()
    for sequence, (sample, kind, note) in enumerate(events, 1):
        writer.writerow(dict(sample=sample, kind=kind, note=note,
            velocity=100 if kind == 'on' else 0, voice_id=0, sequence=sequence))
    return stream.getvalue()


class PortablePendingStringTrialTests(unittest.TestCase):
    def execute(self, root, *, after=None, events=BETTER_EVENTS, drift=None,
                baseline_events=BASE_EVENTS):
        before = replay_text(target=1, transitions=len(baseline_events))
        args = fixtures.PortableEvidenceRetentionTrialTests().fixture(root, baseline_text=before)
        reference_path = args[3]
        reference = json.loads(reference_path.read_text())
        raw = root / 'baseline-midi.tsv'
        raw.write_text(midi_text(baseline_events))
        reference['runs']['reference-off']['traces'] = {
            'midi-event': {'raw_sha256': digest(raw)}}
        reference['runs']['trial-on'] = reference['runs']['reference-off'].copy()
        reference_path.write_text(json.dumps(reference))
        calls = []

        def replay(command, *, stdout, stderr, check, timeout):
            self.assertTrue(check)
            self.assertGreater(timeout, 0)
            index = len(calls)
            self.assertEqual(trial.COLLISION_FLAG in command, index > 0)
            self.assertEqual(trial.FLAG in command, index == 2)
            self.assertNotIn('--diagnostic-direct-evidence-retention', command)
            self.assertNotIn('--candidate-trace', command)
            text = before if index < 2 else (after or replay_text(target=2, transitions=len(events)))
            if drift == ('snapshot', index):
                text += '\n'
            stdout.write(text)
            raw_text = midi_text(baseline_events if index < 2 else events)
            if drift == ('midi', index):
                raw_text = raw_text.replace('100', '99')
            Path(command[command.index('--midi-event-trace') + 1]).write_text(raw_text)
            calls.append(command)

        with patch.object(trial, 'HELD_LABEL', LABEL), patch.object(trial, 'HELD_BASELINE',
                dict(exact_held_samples=80, note_ons_inside_label=2)), \
                patch.object(trial.subprocess, 'run', side_effect=replay):
            trial.run(*args)
        return json.loads((args[-1] / 'report.json').read_text()), calls

    def test_three_conditions_keep_saved_identities_and_measure_real_holds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report, calls = self.execute(root)
            self.assertEqual(len(calls), 3)
            self.assertTrue(report['full_recording_screen_pass'])
            self.assertFalse(report['promotion_accepted'])
            self.assertFalse(report['installed_output_changed'])
            self.assertEqual(report['runs']['current-on']['held_label']['exact_held_samples'], 80)
            self.assertEqual(report['runs']['trial-on']['held_label']['exact_held_samples'], 159)
            self.assertEqual(report['runs']['trial-on']['held_label']['note_ons_inside_label'], 1)
            self.assertEqual(report['held_sample_losses'], [])
            self.assertEqual(len(list((root / 'output').glob('*/midi-event.tsv.gz'))), 3)
            self.assertFalse(list((root / 'output').glob('*/midi-event.tsv')))

    def test_baseline_snapshot_or_raw_midi_drift_stops_trial(self):
        for kind in ('snapshot', 'midi'):
            for index in (0, 1):
                with self.subTest(kind=kind, condition=index), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    with self.assertRaisesRegex(ValueError, 'saved snapshot or raw MIDI reference'):
                        self.execute(root, drift=(kind, index))
                    report = json.loads((root / 'output/report.json').read_text())
                    self.assertEqual(report['state'], 'failed')
                    self.assertTrue(report['final'])
                    self.assertNotIn('trial-on', report['runs'])

    def test_unchanged_hold_rejected_even_if_snapshot_matches_increase(self):
        with tempfile.TemporaryDirectory() as temp:
            report, _ = self.execute(Path(temp), events=BASE_EVENTS)
            self.assertFalse(report['held_label_improved'])
            self.assertFalse(report['full_recording_screen_pass'])

    def test_aggregate_gain_does_not_hide_passage_loss(self):
        with tempfile.TemporaryDirectory() as temp:
            report, _ = self.execute(Path(temp), after=replay_text(target=3, other=0))
            self.assertTrue(report['held_label_improved'])
            self.assertGreater(report['comparisons']['current-on']['delta']['matched'], 0)
            self.assertFalse(report['comparisons']['current-on']['gate_pass'])
            self.assertFalse(report['full_recording_screen_pass'])

    def test_false_notes_reject_an_improved_hold(self):
        with tempfile.TemporaryDirectory() as temp:
            report, _ = self.execute(Path(temp), after=replay_text(target=2, false_notes=1))
            self.assertTrue(report['held_label_improved'])
            self.assertFalse(report['full_recording_screen_pass'])

    def test_invalid_pairing_cannot_claim_duration_improvement(self):
        with tempfile.TemporaryDirectory() as temp:
            report, _ = self.execute(Path(temp), events=((32, 'on', 42), (191, 'off', 43)))
            self.assertFalse(report['runs']['trial-on']['lifecycle']['coverage_valid'])
            self.assertNotIn('held_label', report['runs']['trial-on'])
            self.assertIsNone(report['held_sample_losses'])
            self.assertFalse(report['full_recording_screen_pass'])

    def test_other_passage_hold_loss_rejects_target_improvement(self):
        baseline = ((0, 'on', 60), (32, 'off', 60), *BASE_EVENTS)
        with tempfile.TemporaryDirectory() as temp:
            report, _ = self.execute(Path(temp), baseline_events=baseline)
            self.assertTrue(report['held_label_improved'])
            self.assertTrue(report['held_sample_losses'])
            self.assertFalse(report['full_recording_screen_pass'])


if __name__ == '__main__':
    unittest.main()
