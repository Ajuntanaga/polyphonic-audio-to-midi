import csv
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_portable_evidence_retention_trial as fixtures
from tests.test_portable_evidence_retention_trial import calibrated_rows, replay_text
from tests.test_portable_routing_trace import routing_rows, snapshots, write_rows
from tools.midi_lifecycle_analysis import EVENT_FIELDS
from tools.portable_assignment_trace import digest
from tools.portable_midi_lane_trace import candidate_frames, raw_lane_history, run


def event(sample, kind, note, sequence):
    return dict(sample=sample, kind=kind, note=note, velocity=25 if kind == 'on' else 0,
                voice_id=0, sequence=sequence)


EVENTS = [event(63, 'on', 48, 0), event(127, 'on', 47, 1), event(191, 'off', 48, 2)]


def candidates(note):
    result = []
    for route, calibrated in zip(routing_rows(), calibrated_rows()):
        row = dict(route, **calibrated)
        row.update(note=str(note), selection='4', active='1', assigned_mask='1',
                   rescue_mask='0', selector_mask='1', selected_or_coasting='47,48')
        result.append(row)
    return result


class PortableMidiLaneTraceTests(unittest.TestCase):
    def test_old_raw_owner_survives_new_pitch_and_its_off_removes_only_itself(self):
        result = raw_lane_history(EVENTS, lane=0, start=64, end=192)
        self.assertEqual(result['unreleased_raw_note_ons_at_window_start'], [EVENTS[0]])
        first, second = result['events']
        self.assertEqual(first['unreleased_raw_note_ons_after'], EVENTS[:2])
        self.assertEqual(second['unreleased_raw_note_ons_before'], EVENTS[:2])
        self.assertEqual(second['unreleased_raw_note_ons_after'], [EVENTS[1]])
        self.assertFalse(second['same_pitch_pairing_ambiguous'])

    def test_repeated_same_pitch_is_retained_and_pairing_ambiguity_is_explicit(self):
        events = [event(1, 'on', 48, 0), event(2, 'on', 48, 1), event(3, 'off', 48, 2)]
        result = raw_lane_history(events, lane=0, start=0, end=4)['events']
        self.assertFalse(result[0]['same_pitch_pairing_ambiguous'])
        self.assertTrue(result[1]['same_pitch_pairing_ambiguous'])
        self.assertTrue(result[2]['same_pitch_pairing_ambiguous'])
        self.assertEqual(result[2]['unreleased_raw_note_ons_after'], [events[1]])

    def test_snapshot_clocks_require_complete_current_observations(self):
        frames = candidate_frames(candidates(47), snapshots(), note=47, start=0, end=192)
        self.assertEqual(frames[0]['routing']['tick'], 0)
        self.assertEqual(frames[1]['routing']['tick'], 2)
        self.assertEqual(frames[1]['tracking']['active'], 1)
        for field, value in (('route_tick', '1'), ('tick', '1'), ('note', '48')):
            rows = candidates(47)
            rows[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                candidate_frames(rows, snapshots(), note=47, start=0, end=192)
        for rows, outcomes in ((candidates(47)[:-1], snapshots()),
                (candidates(47) + [candidates(47)[0]], snapshots()),
                (candidates(47), snapshots()[:-1]),
                (candidates(47), snapshots() + [snapshots()[0]])):
            with self.subTest(rows=len(rows), outcomes=len(outcomes)), self.assertRaises(ValueError):
                candidate_frames(rows, outcomes, note=47, start=0, end=192)

    def fixture(self, root):
        text = replay_text(transitions=3)
        args = fixtures.PortableEvidenceRetentionTrialTests().fixture(root, baseline_text=text)
        return args, text

    def replay_stub(self, text, *, drift_note=None, missing_target=False, stream_drift=False):
        def replay(command, *, stdout, stderr, check, timeout):
            self.assertTrue(check)
            self.assertGreater(timeout, 0)
            self.assertFalse(any(arg.startswith('--diagnostic-') for arg in command))
            note = int(command[command.index('--candidate-trace-note') + 1])
            self.assertIn(note, (47, 48))
            stdout.write(text + ('\n' if note == drift_note else ''))
            start = float(command[command.index('--candidate-trace-start') + 1]) * 96000
            rows = [row for row in candidates(note) if int(row['sample']) >= start]
            write_rows(Path(command[command.index('--candidate-trace') + 1]), rows)
            outcomes = snapshots()
            if stream_drift and note == 48:
                # Outside the retained window: complete-stream equality must still catch it.
                outcomes[0]['quiet'] = '1'
            write_rows(Path(command[command.index('--outcome-trace') + 1]), outcomes)
            events = [dict(item) for item in EVENTS]
            if missing_target:
                events[1]['note'] = 49
            path = Path(command[command.index('--midi-event-trace') + 1])
            with path.open('w', newline='') as stream:
                stream.write('# m3_midi_events_v1\n')
                writer = csv.DictWriter(stream, fieldnames=EVENT_FIELDS, delimiter='\t')
                writer.writeheader()
                writer.writerows(events)
        return replay

    def execute(self, args, stub):
        with patch('tools.portable_midi_lane_trace.WINDOW', (64, 192)), patch(
                'tools.portable_midi_lane_trace.TARGET_EVENTS', EVENTS[1:]), patch(
                'tools.portable_midi_lane_trace.subprocess.run', side_effect=stub) as replay:
            run(*args)
        return replay

    def test_two_observations_preserve_reference_and_retain_only_bounded_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            args, text = self.fixture(Path(directory))
            replay = self.execute(args, self.replay_stub(text))
            self.assertEqual(replay.call_count, 2)
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertEqual(report['state'], 'completed')
            self.assertTrue(report['complete_midi_and_outcome_identical'])
            for key in ('promotion_accepted', 'runtime_rule_changed', 'installed_output_changed'):
                self.assertFalse(report[key])
            for stem, result in report['runs'].items():
                self.assertTrue(result['reference_bit_identical'])
                self.assertEqual(len(result['frames']), 2)
                self.assertEqual(result['raw_lane_history']['unreleased_raw_note_ons_at_window_start'],
                                 [EVENTS[0]])
                for kind, trace in result['traces'].items():
                    compressed = args[-1] / stem / trace['file']
                    self.assertEqual(digest(compressed), trace['sha256'])
                    self.assertFalse(compressed.with_suffix('').exists())
                    with gzip.open(compressed, 'rt') as stream:
                        rows = list(csv.DictReader((line for line in stream
                                                    if not line.startswith('#')), delimiter='\t'))
                    self.assertEqual([int(row['sample']) for row in rows], [127, 191])

    def test_output_drift_stops_either_observation(self):
        for note in (47, 48):
            with self.subTest(note=note), tempfile.TemporaryDirectory() as directory:
                args, text = self.fixture(Path(directory))
                with self.assertRaisesRegex(ValueError, 'differs from the historical OFF replay'):
                    self.execute(args, self.replay_stub(text, drift_note=note))
                report = json.loads((args[-1] / 'report.json').read_text())
                self.assertTrue(report['final'])
                self.assertEqual(report['state'], 'failed')
                self.assertFalse(report['promotion_accepted'])

    def test_missing_conflict_and_out_of_window_capture_drift_are_rejected(self):
        for kwargs, message in ((dict(missing_target=True), 'conflict event changed'),
                                (dict(stream_drift=True), 'complete MIDI or outcome stream')):
            with self.subTest(case=kwargs), tempfile.TemporaryDirectory() as directory:
                args, text = self.fixture(Path(directory))
                with self.assertRaisesRegex(ValueError, message):
                    self.execute(args, self.replay_stub(text, **kwargs))
                report = json.loads((args[-1] / 'report.json').read_text())
                self.assertEqual(report['state'], 'failed')
                self.assertFalse(report['promotion_accepted'])


if __name__ == '__main__':
    unittest.main()
