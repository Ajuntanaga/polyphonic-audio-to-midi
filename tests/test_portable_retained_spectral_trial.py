import csv
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_portable_evidence_retention_trial as fixtures
from tests.test_portable_evidence_retention_trial import replay_text
from tests.test_portable_midi_lane_trace import EVENTS, candidates, event
from tests.test_portable_routing_trace import snapshots, write_rows
from tools.midi_lifecycle_analysis import EVENT_FIELDS
from tools.portable_retained_spectral_trial import COLLISION_FLAG, FLAG, raw_conflicts, run


CLEAN_EVENTS = [event(63, 'on', 48, 0), event(127, 'off', 48, 1),
                event(191, 'on', 47, 2)]


class PortableRetainedSpectralTrialTests(unittest.TestCase):
    def test_conflicting_on_does_not_erase_the_old_owner(self):
        result = raw_conflicts(EVENTS)
        self.assertEqual(result['counts']['cross_pitch_on_before_release'], 1)
        self.assertEqual(result['counts']['off_without_raw_on'], 0)
        self.assertEqual(result['examples'][0]['unreleased_raw_note_ons'], [EVENTS[0]])
        self.assertEqual(result['raw_note_ons_open_at_eof'], [EVENTS[1]])
        self.assertEqual(sum(raw_conflicts(CLEAN_EVENTS)['counts'].values()), 0)

    def test_repeat_unmatched_off_and_unassigned_events_are_separate(self):
        events = [event(1, 'on', 48, 0), event(2, 'on', 48, 1),
                  event(3, 'off', 48, 2), event(4, 'off', 47, 3),
                  dict(event(5, 'on', 49, 4), voice_id=255, velocity=0)]
        result = raw_conflicts(events)
        self.assertEqual(result['counts'], dict(cross_pitch_on_before_release=0,
            repeated_pitch_on_before_release=1, off_without_raw_on=1,
            zero_velocity_on=1, unassigned_on=1))
        self.assertEqual(result['raw_note_ons_open_at_eof'], [events[1], events[4]])

    def fixture(self, root):
        baseline = replay_text(target=1, other=1, transitions=3)
        args = fixtures.PortableEvidenceRetentionTrialTests().fixture(root, baseline_text=baseline)
        return args, baseline

    def stub(self, baseline, *, trial=None, trial_events=CLEAN_EVENTS, drift=False,
             flag=FLAG):
        def replay(command, *, stdout, stderr, check, timeout):
            self.assertTrue(check)
            self.assertGreater(timeout, 0)
            flags = [arg for arg in command if arg.startswith('--diagnostic-')]
            enabled = flag in command
            self.assertEqual(flags, [flag] if enabled else [])
            text = trial if enabled and trial is not None else baseline
            stdout.write(text + ('\n' if drift and not enabled else ''))
            rows = [row for row in candidates(48) if int(row['sample']) >= 64]
            write_rows(Path(command[command.index('--candidate-trace') + 1]), rows)
            write_rows(Path(command[command.index('--outcome-trace') + 1]), snapshots())
            path = Path(command[command.index('--midi-event-trace') + 1])
            with path.open('w', newline='') as stream:
                stream.write('# m3_midi_events_v1\n')
                writer = csv.DictWriter(stream, fieldnames=EVENT_FIELDS, delimiter='\t')
                writer.writeheader()
                writer.writerows(trial_events if enabled else EVENTS)
        return replay

    def execute(self, args, stub, **kwargs):
        with patch('tools.portable_retained_spectral_trial.WINDOW', (64, 192)), patch(
                'tools.portable_retained_spectral_trial.COASTING_WINDOW', (64, 192)), patch(
                'tools.portable_retained_spectral_trial.PENDING_WINDOW', (64, 192)), patch(
                'tools.portable_retained_spectral_trial.TARGET_EVENTS', EVENTS[1:]), patch(
                'tools.portable_retained_spectral_trial.subprocess.run', side_effect=stub) as replay:
            run(*args, **kwargs)
        return replay

    def test_only_on_changes_policy_and_full_midi_survives_window_reduction(self):
        with tempfile.TemporaryDirectory() as directory:
            args, baseline = self.fixture(Path(directory))
            replay = self.execute(args, self.stub(baseline))
            self.assertEqual(replay.call_count, 2)
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertEqual(report['state'], 'completed')
            self.assertTrue(report['off_reference_bit_identical'])
            self.assertTrue(report['full_recording_screen_pass'])
            self.assertTrue(report['recorded_lane_window_resolved'])
            self.assertEqual(report['decision'], 'eligible for wider validation')
            self.assertEqual(report['raw_midi_delta']['cross_pitch_on_before_release'], -1)
            self.assertFalse(report['promotion_accepted'])
            self.assertFalse(report['installed_output_changed'])
            for stem, result in report['runs'].items():
                for kind, trace in result['traces'].items():
                    path = args[-1] / stem / trace['file']
                    self.assertFalse(path.with_suffix('').exists())
                    with gzip.open(path, 'rt') as stream:
                        rows = list(csv.DictReader((line for line in stream
                            if not line.startswith('#')), delimiter='\t'))
                    self.assertEqual([int(row['sample']) for row in rows],
                        [63, 127, 191] if kind == 'midi-event' else [127, 191])

    def test_collision_policy_uses_only_its_flag_and_keeps_passage_gate(self):
        for lost_match in (False, True):
            with self.subTest(lost_match=lost_match), tempfile.TemporaryDirectory() as directory:
                args, baseline = self.fixture(Path(directory))
                trial = replay_text(target=0, other=3, transitions=3) if lost_match else baseline
                replay = self.execute(args, self.stub(baseline, trial=trial, flag=COLLISION_FLAG),
                                      policy='spectral-lane-collision')
                self.assertEqual(replay.call_count, 2)
                report = json.loads((args[-1] / 'report.json').read_text())
                self.assertEqual(report['schema'], 'm3_spectral_lane_collision_trial_v1')
                self.assertEqual(report['diagnostic_flag'], COLLISION_FLAG)
                self.assertEqual(report['policy_name'], 'spectral-lane-collision')
                self.assertTrue(report['off_reference_bit_identical'])
                self.assertTrue(report['recorded_lane_window_resolved'])
                self.assertTrue(report['coasting_lane_window_resolved'])
                self.assertTrue(report['pending_lane_window_resolved'])
                self.assertEqual(report['trial_revision'], 'independent_output_ownership')
                self.assertEqual(report['emitted_midi_labeled_matches'], 'not measured')
                self.assertEqual(report['full_recording_screen_pass'], not lost_match)
                self.assertFalse(report['promotion_accepted'])
                self.assertFalse(report['installed_output_changed'])

    def test_off_drift_stops_before_on(self):
        with tempfile.TemporaryDirectory() as directory:
            args, baseline = self.fixture(Path(directory))
            with patch('tools.portable_retained_spectral_trial.WINDOW', (64, 192)), patch(
                    'tools.portable_retained_spectral_trial.subprocess.run',
                    side_effect=self.stub(baseline, drift=True)) as replay:
                with self.assertRaisesRegex(ValueError, 'OFF reference differs'):
                    run(*args)
                self.assertEqual(replay.call_count, 1)
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertEqual(report['state'], 'failed')
            self.assertTrue(report['final'])

    def test_aggregate_improvement_cannot_hide_coasting_lane_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            args, baseline = self.fixture(Path(directory))
            # Baseline has two conflicts on lane zero; trial clears that lane,
            # but one remaining lane-one collision must still reject the trial.
            baseline_events = [event(63, 'on', 48, 0), event(127, 'on', 47, 1),
                               event(191, 'on', 46, 2)]
            trial_events = [dict(row, voice_id=1) for row in EVENTS]
            with patch('tests.test_portable_retained_spectral_trial.EVENTS', baseline_events):
                self.execute(args, self.stub(baseline, trial_events=trial_events,
                                            flag=COLLISION_FLAG),
                             policy='spectral-lane-collision')
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertTrue(report['raw_conflicts_reduced'])
            self.assertTrue(report['recorded_lane_window_resolved'])
            self.assertFalse(report['coasting_lane_window_resolved'])
            self.assertFalse(report['full_recording_screen_pass'])
            self.assertEqual(report['runs']['trial-on']['coasting_lane_window_conflicts'], 1)
            self.assertEqual(report['decision'], 'rejected')

    def test_smoother_raw_midi_cannot_offset_lost_label_or_extra_false_notes(self):
        for trial in (replay_text(target=0, other=3, transitions=3),
                      replay_text(target=1, other=1, transitions=3, false_notes=1)):
            with self.subTest(trial=trial), tempfile.TemporaryDirectory() as directory:
                args, baseline = self.fixture(Path(directory))
                self.execute(args, self.stub(baseline, trial=trial))
                report = json.loads((args[-1] / 'report.json').read_text())
                self.assertTrue(report['raw_conflicts_reduced'])
                self.assertFalse(report['comparison']['gate_pass'])
                self.assertFalse(report['full_recording_screen_pass'])
                self.assertEqual(report['decision'], 'rejected')

    def test_other_windows_cannot_hide_a_pending_attack_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            args, baseline = self.fixture(Path(directory))
            original = raw_conflicts

            def extra_off_conflict(events):
                result = original(events)
                if extra_off_conflict.first:
                    result['counts']['cross_pitch_on_before_release'] += 1
                    extra_off_conflict.first = False
                return result

            extra_off_conflict.first = True
            # A same-sample pair on another lane clears both earlier windows
            # but still fails the separately observed pending-attack window.
            pending_events = [dict(event(127, 'on', note, sequence), voice_id=2)
                              for sequence, note in enumerate((36, 37))]
            pending_events.append(dict(event(191, 'off', 36, 2), voice_id=2))
            with patch('tools.portable_retained_spectral_trial.PENDING_LANE', 2), patch(
                    'tools.portable_retained_spectral_trial.raw_conflicts',
                    side_effect=extra_off_conflict):
                self.execute(args, self.stub(baseline, trial_events=pending_events,
                                            flag=COLLISION_FLAG),
                             policy='spectral-lane-collision')
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertTrue(report['raw_conflicts_reduced'])
            self.assertTrue(report['recorded_lane_window_resolved'])
            self.assertTrue(report['coasting_lane_window_resolved'])
            self.assertFalse(report['pending_lane_window_resolved'])
            self.assertEqual(report['runs']['trial-on']['pending_lane_window_conflicts'], 1)
            self.assertFalse(report['full_recording_screen_pass'])
            self.assertEqual(report['decision'], 'rejected')

    def test_other_improvements_cannot_hide_the_recorded_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            args, baseline = self.fixture(Path(directory))
            original = raw_conflicts

            def extra_earlier_off_conflict(events):
                result = original(events)
                if extra_earlier_off_conflict.first:
                    result['counts']['cross_pitch_on_before_release'] += 1
                    extra_earlier_off_conflict.first = False
                return result

            extra_earlier_off_conflict.first = True
            with patch('tools.portable_retained_spectral_trial.raw_conflicts',
                       side_effect=extra_earlier_off_conflict):
                self.execute(args, self.stub(baseline, trial_events=EVENTS))
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertTrue(report['raw_conflicts_reduced'])
            self.assertFalse(report['recorded_lane_window_resolved'])
            self.assertFalse(report['full_recording_screen_pass'])

    def test_unchanged_conflicts_or_new_unmatched_off_do_not_pass(self):
        for events in (EVENTS, [event(63, 'on', 48, 0), event(127, 'off', 48, 1),
                               event(191, 'off', 47, 2)]):
            with self.subTest(events=events), tempfile.TemporaryDirectory() as directory:
                args, baseline = self.fixture(Path(directory))
                self.execute(args, self.stub(baseline, trial_events=events))
                report = json.loads((args[-1] / 'report.json').read_text())
                self.assertTrue(report['comparison']['gate_pass'])
                self.assertFalse(report['full_recording_screen_pass'])
                self.assertEqual(report['decision'], 'rejected')


if __name__ == '__main__':
    unittest.main()
