import csv
from pathlib import Path
import tempfile
import unittest

from tools.frozen_cue_corpus_gate import COUNTS, LABEL_FIELDS
from tools.midi_lifecycle_analysis import EVENT_FIELDS, analyze_trace, read_events, summarize


def event(sample, kind, note=60, voice=0, velocity=None, sequence=None):
    return dict(sample=sample, kind=kind, note=note, voice_id=voice,
                sequence=sample if sequence is None else sequence,
                velocity=(100 if kind == 'on' else 0) if velocity is None else velocity)


def label(index=0, start=20, end=120, note=60, mask=1):
    return dict(label_index=index, start_sample=start, end_sample=end,
                midi_note=note, string_mask=mask, calibration_pass=0, labeled=10, matched=10)


def trace(path, events):
    with path.open('w', newline='') as stream:
        stream.write('# m3_midi_events_v1\n')
        writer = csv.DictWriter(stream, fieldnames=EVENT_FIELDS, delimiter='\t')
        writer.writeheader()
        writer.writerows(events)


class MidiLifecycleTests(unittest.TestCase):
    def summary(self, events, labels=None, samples=200):
        return summarize(events, [label()] if labels is None else labels,
                         sample_count=samples, sample_rate=96000)

    def test_events_before_and_after_label_preserve_the_full_hold(self):
        result = self.summary([event(10, 'on'), event(150, 'off')])
        row = result['labels'][0]
        self.assertEqual(row['exact_held_samples'], 100)
        self.assertEqual(row['first_exact_hold_delay_samples'], 0)
        self.assertEqual(row['note_ons_inside_label'], 0)
        self.assertEqual(result['closed_note_duration_samples'],
                         dict(minimum=140, median=140, maximum=140))
        self.assertTrue(result['balanced_at_recording_end'])
        self.assertEqual(result['samples_after_last_label'], 80)
        self.assertEqual(result['host_delivery'], 'not measured')

    def test_matched_tuner_preview_without_note_on_has_no_midi_hold(self):
        result = self.summary([])
        self.assertEqual(result['exact_held_samples'], 0)
        self.assertEqual(result['labels'][0]['unmatched_hold_samples'], 100)
        self.assertIsNone(result['labels'][0]['first_exact_hold_delay_samples'])

    def test_unison_requires_simultaneous_expected_lanes_and_no_extra_lane(self):
        events = [event(0, 'on', voice=0), event(10, 'on', voice=1),
                  event(20, 'on', voice=2), event(50, 'on', voice=3),
                  event(60, 'off', voice=3), event(80, 'off', voice=0),
                  event(90, 'off', voice=1), event(100, 'off', voice=2)]
        result = self.summary(events, [label(start=0, end=100, mask=7)])
        row = result['labels'][0]
        self.assertEqual(row['exact_held_samples'], 50)
        self.assertEqual(row['longest_exact_hold_samples'], 30)
        self.assertEqual(row['exact_hold_segments'], 2)
        self.assertEqual(row['first_exact_hold_delay_samples'], 20)
        self.assertEqual(row['note_ons_inside_label'], 4)

    def test_unassigned_identities_are_pitch_keyed_and_do_not_prove_a_string_mask(self):
        events = [event(10, 'on', voice=255), event(15, 'on', note=61, voice=255),
                  event(20, 'on', note=62, voice=7), event(130, 'off', voice=255),
                  event(140, 'off', note=61, voice=255), event(150, 'off', note=62, voice=7)]
        labels = [label(mask=1), label(1, mask=0), label(2, note=61, mask=0),
                  label(3, note=62, mask=128)]
        result = self.summary(events, labels)
        self.assertEqual(result['event_error_counts'], {})
        self.assertEqual([row['exact_held_samples'] for row in result['labels']], [0, 100, 100, 100])
        self.assertTrue(result['balanced_at_recording_end'])

    def test_open_at_eof_is_retained_without_inventing_a_note_off(self):
        result = self.summary([event(60, 'on')])
        self.assertFalse(result['balanced_at_recording_end'])
        self.assertEqual(result['note_offs'], 0)
        self.assertEqual(result['open_at_recording_end'], [dict(
            voice_id=0, note=60, start_sample=60, observed_hold_samples=140)])
        self.assertEqual(result['labels'][0]['exact_held_samples'], 60)
        self.assertEqual(result['acceptance_target'], 'not measured')

    def test_pitch_only_hold_remains_continuous_when_the_lane_mask_changes(self):
        events = [event(10, 'on'), event(50, 'on', voice=1),
                  event(70, 'off'), event(150, 'off', voice=1)]
        row = self.summary(events, [label(mask=0)])['labels'][0]
        self.assertEqual(row['exact_held_samples'], 100)
        self.assertEqual(row['longest_exact_hold_samples'], 100)
        self.assertEqual(row['exact_hold_segments'], 1)

    def test_pairing_errors_suppress_coverage_instead_of_guessing(self):
        cases = [(event(10, 'off'), 'note_off_without_matching_note_on'),
                 (event(10, 'on', velocity=0), 'zero_velocity_note_on')]
        for bad, kind in cases:
            with self.subTest(kind=kind):
                result = self.summary([bad])
                self.assertEqual(result['event_error_counts'][kind], 1)
                self.assertFalse(result['coverage_valid'])
                self.assertIsNone(result['exact_held_samples'])
                self.assertIsNone(result['labels'])
        result = self.summary([event(10, 'on'), event(20, 'on', note=61)])
        self.assertEqual(result['event_error_counts']['note_on_before_lane_release'], 1)
        self.assertIsNone(result['closed_note_duration_samples'])

    def test_same_sample_off_then_on_keeps_coverage_but_records_retrigger(self):
        result = self.summary([event(10, 'on'), event(50, 'off'),
                               event(50, 'on'), event(150, 'off')])
        row = result['labels'][0]
        self.assertEqual(row['exact_held_samples'], 100)
        self.assertEqual(row['exact_hold_segments'], 1)
        self.assertEqual(row['note_ons_inside_label'], 1)
        self.assertEqual(result['note_ons'], 2)
        self.assertEqual(result['closed_note_duration_samples'],
                         dict(minimum=40, median=70, maximum=100))

    def test_trace_completeness_clock_order_and_native_voice_range(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.tsv'
            events = [event(1, 'on', voice=7), event(2, 'on', note=61, voice=255)]
            trace(path, events)
            self.assertEqual(read_events(path, sample_count=200, transition_count=2), events)
            with self.assertRaisesRegex(ValueError, 'transition count'):
                read_events(path, sample_count=200, transition_count=3)
            same_sample = [event(1, 'off', sequence=0), event(1, 'on', sequence=1)]
            trace(path, same_sample)
            self.assertEqual(read_events(path, sample_count=200, transition_count=2), same_sample)
            for events in ([event(200, 'on')], [event(1, 'on', voice=8)],
                           [event(1, 'on', note=128)], [event(1, 'other')],
                           [event(10, 'on'), event(9, 'off')],
                           [event(1, 'on'), event(2, 'off', sequence=1)],
                           [event(1, 'on', sequence=2), event(2, 'off', sequence=1)]):
                trace(path, events)
                with self.subTest(events=events), self.assertRaises(ValueError):
                    read_events(path, sample_count=200, transition_count=len(events))
            path.write_text('# m3_midi_events_v1\nsample\tkind\n1\ton\n')
            with self.assertRaisesRegex(ValueError, 'header'):
                read_events(path, sample_count=200, transition_count=1)

    def test_analysis_uses_native_sample_clock_and_complete_transition_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replay, midi = root / 'replay.tsv', root / 'midi.tsv'
            trace(midi, [event(10, 'on'), event(150, 'off')])
            aggregate = dict.fromkeys(COUNTS, 0)
            aggregate.update(fingerprint='0123456789abcdef', labeled=10, matched=10,
                             sample_rate=96000, samples=200, transitions=2)
            with replay.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=aggregate, delimiter='\t')
                writer.writeheader()
                writer.writerow(aggregate)
                writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS, delimiter='\t')
                writer.writeheader()
                writer.writerow(label())
            result = analyze_trace(midi, replay)
            self.assertEqual(result['sample_rate'], 96000)
            self.assertEqual(result['sample_count'], 200)
            self.assertEqual(result['exact_held_samples'], 100)
            self.assertNotIn('raw_midi', result)
            raw = analyze_trace(midi, replay, include_raw_conflicts=True)
            self.assertEqual(sum(raw['raw_midi']['counts'].values()), 0)
            self.assertEqual(raw['exact_held_samples'], result['exact_held_samples'])
            trace(midi, [event(10, 'on')])
            with self.assertRaisesRegex(ValueError, 'transition count'):
                analyze_trace(midi, replay, include_raw_conflicts=True)

    def test_annotations_cannot_extend_past_the_observed_recording(self):
        with self.assertRaisesRegex(ValueError, 'annotation interval'):
            self.summary([], [label(end=201)])


if __name__ == '__main__':
    unittest.main()
