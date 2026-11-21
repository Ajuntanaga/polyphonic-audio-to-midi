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

    def pitch_summary(self, events, labels=None, samples=200):
        return summarize(events, [label()] if labels is None else labels,
                         sample_count=samples, sample_rate=96000,
                         include_output_safety=True, include_group_coverage=True,
                         include_pitch_set_coverage=True)

    def test_pitch_coverage_is_independent_of_string_assignment_and_additive(self):
        labels = [label(i, note=60 + i, mask=1 << i) for i in range(3)]
        events = [event(0, 'on', note=60 + i, voice=3 + i) for i in range(3)]
        result = self.pitch_summary(events, labels)
        coverage = result.pop('pitch_set_coverage')
        self.assertEqual(result, summarize(events, labels, sample_count=200, sample_rate=96000,
                                          include_output_safety=True, include_group_coverage=True))
        self.assertEqual(result['exact_held_samples'], 0)
        self.assertEqual(result['output_safety']['counts']['false_wrong_string_voice_samples'], 300)
        self.assertEqual(coverage['totals']['expected_pitch_samples'], 300)
        self.assertEqual(coverage['totals']['present_pitch_samples'], 300)
        self.assertEqual(coverage['totals']['all_expected_pitches_samples'], 100)
        self.assertEqual(coverage['totals']['exact_pitch_set_samples'], 100)
        self.assertEqual(coverage['totals']['one_voice_per_pitch_samples'], 100)

    def test_pitch_coverage_separates_extra_pitch_and_duplicate_voice(self):
        events = [event(0, 'on'), event(30, 'on', note=65, voice=1),
                  event(50, 'off', note=65, voice=1), event(60, 'on', voice=2),
                  event(80, 'off', voice=2), event(150, 'off')]
        coverage = self.pitch_summary(events)['pitch_set_coverage']
        totals = coverage['totals']
        self.assertEqual(totals['all_expected_pitches_samples'], 100)
        self.assertEqual(totals['exact_pitch_set_samples'], 80)
        self.assertEqual(totals['one_voice_per_pitch_samples'], 60)
        self.assertEqual(totals['extra_pitch_voice_samples'], 20)
        self.assertEqual(totals['duplicate_expected_pitch_voice_samples'], 20)
        self.assertEqual(coverage['unlabeled_gap_voice_samples'], 50)
        self.assertEqual(coverage['intervals'][0]['longest_all_expected_hold_samples'], 100)

    def test_pitch_coverage_partitions_overlap_without_double_counting_same_pitch_labels(self):
        labels = [label(0, 0, 100), label(1, 30, 70, note=64, mask=2),
                  label(2, 20, 80, mask=4)]
        events = [event(0, 'on'), event(40, 'on', note=64, voice=1),
                  event(60, 'off', note=64, voice=1), event(100, 'off')]
        coverage = self.pitch_summary(events, labels)['pitch_set_coverage']
        totals = coverage['totals']
        self.assertEqual(totals['annotated_samples'], 100)
        self.assertEqual(totals['expected_pitch_samples'], 140)
        self.assertEqual(totals['present_pitch_samples'], 120)
        self.assertEqual(totals['all_expected_pitches_samples'], 80)
        chord = coverage['by_distinct_pitch_count']['2']
        self.assertEqual(chord['annotated_samples'], 40)
        self.assertEqual(chord['all_expected_pitches_samples'], 20)
        self.assertEqual(len(coverage['intervals']), 5)
        row = coverage['intervals'][2]
        self.assertEqual(row['first_all_expected_hold_delay_samples'], 10)
        self.assertEqual(row['longest_all_expected_hold_samples'], 20)

    def test_pitch_coverage_does_not_rename_four_string_unison_as_four_pitch_chord(self):
        labels = [label(i, mask=1 << i) for i in range(4)]
        events = [event(0, 'on', voice=i) for i in range(4)]
        result = self.pitch_summary(events, labels)
        coverage = result['pitch_set_coverage']
        self.assertEqual(set(coverage['by_distinct_pitch_count']), {'1'})
        self.assertEqual(coverage['totals']['expected_pitch_samples'], 100)
        self.assertEqual(coverage['totals']['exact_pitch_set_samples'], 100)
        self.assertEqual(coverage['totals']['one_voice_per_pitch_samples'], 0)
        self.assertEqual(coverage['totals']['duplicate_expected_pitch_voice_samples'], 300)
        self.assertEqual(result['simultaneous_group_coverage']['exact_group_held_samples'], 100)

    def test_pitch_coverage_unassigned_and_same_sample_retrigger_preserve_presence(self):
        events = [event(20, 'on', voice=255), event(50, 'off', voice=255),
                  event(50, 'on', voice=255), event(120, 'off', voice=255)]
        result = self.pitch_summary(events)
        row = result['pitch_set_coverage']['intervals'][0]
        self.assertEqual(result['exact_held_samples'], 0)
        self.assertEqual(result['labels'][0]['note_ons_inside_label'], 2)
        self.assertEqual(row['all_expected_pitches_samples'], 100)
        self.assertEqual(row['all_expected_hold_segments'], 1)
        self.assertEqual(row['longest_all_expected_hold_samples'], 100)
        self.assertEqual(result['pitch_set_coverage']['unlabeled_gap_voice_samples'], 0)

    def test_pitch_coverage_missing_output_is_not_extra_gap_output(self):
        coverage = self.pitch_summary([])['pitch_set_coverage']
        self.assertEqual(coverage['totals']['expected_pitch_samples'], 100)
        self.assertEqual(coverage['totals']['present_pitch_samples'], 0)
        self.assertEqual(coverage['unlabeled_gap_voice_samples'], 0)
        self.assertIsNone(coverage['intervals'][0]['first_all_expected_hold_delay_samples'])
        empty = self.pitch_summary([event(10, 'on')], [])['pitch_set_coverage']
        self.assertEqual(empty['intervals'], [])
        self.assertEqual(empty['totals']['annotated_samples'], 0)
        self.assertEqual(empty['unlabeled_gap_voice_samples'], 190)

    def test_pitch_coverage_preserves_eof_uncertainty_and_suppresses_invalid_pairing(self):
        result = self.pitch_summary([event(80, 'on')], [label(end=200)])
        self.assertFalse(result['balanced_at_recording_end'])
        self.assertEqual(result['pitch_set_coverage']['totals']['present_pitch_samples'], 120)
        invalid = self.pitch_summary([event(80, 'off')])['pitch_set_coverage']
        self.assertFalse(invalid['valid'])
        self.assertIsNone(invalid['totals'])
        self.assertIsNone(invalid['intervals'])
        self.assertIsNone(invalid['by_distinct_pitch_count'])

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
        self.assertEqual(row['retrigger_note_ons_inside_label'], 1)
        self.assertEqual(result['note_ons'], 2)
        self.assertEqual(result['closed_note_duration_samples'],
                         dict(minimum=40, median=70, maximum=100))

    def test_retrigger_exempts_first_acquisitions_including_unison_lanes(self):
        events = [event(30, 'on'), event(40, 'on', voice=1), event(50, 'off'),
                  event(70, 'on'), event(80, 'off', voice=1),
                  event(90, 'on', voice=1)]
        row = self.summary(events, [label(mask=3)])['labels'][0]
        self.assertEqual(row['note_ons_inside_label'], 4)
        self.assertEqual(row['retrigger_note_ons_inside_label'], 2)
        first = self.summary([event(30, 'on')])['labels'][0]
        self.assertEqual(first['note_ons_inside_label'], 1)
        self.assertEqual(first['retrigger_note_ons_inside_label'], 0)

    def test_retrigger_uses_prelabel_hold_and_half_open_boundaries(self):
        events = [event(10, 'on'), event(20, 'off'), event(20, 'on'),
                  event(119, 'off'), event(120, 'on')]
        row = self.summary(events)['labels'][0]
        self.assertEqual(row['note_ons_inside_label'], 1)
        self.assertEqual(row['retrigger_note_ons_inside_label'], 1)
        first = self.summary([event(10, 'on'), event(19, 'off'),
                              event(20, 'on')])['labels'][0]
        self.assertEqual(first['retrigger_note_ons_inside_label'], 0)

    def test_retrigger_tracks_unassigned_pitches_independently(self):
        events = [event(10, 'on', note=61, voice=255),
                  event(20, 'on', voice=255), event(30, 'off', voice=255),
                  event(40, 'on', voice=255)]
        row = self.summary(events, [label(mask=0)])['labels'][0]
        self.assertEqual(row['note_ons_inside_label'], 2)
        self.assertEqual(row['retrigger_note_ons_inside_label'], 1)

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
            grouped = analyze_trace(midi, replay, include_group_coverage=True)
            groups = grouped.pop('simultaneous_group_coverage')
            self.assertEqual(grouped, result)
            self.assertEqual(groups['exact_group_held_samples'], 100)
            trace(midi, [event(10, 'on')])
            with self.assertRaisesRegex(ValueError, 'transition count'):
                analyze_trace(midi, replay, include_raw_conflicts=True)

    def test_annotations_cannot_extend_past_the_observed_recording(self):
        with self.assertRaisesRegex(ValueError, 'annotation interval'):
            self.summary([], [label(end=201)])

    def test_output_safety_counts_disjoint_voice_durations(self):
        events = [event(0, 'on'), event(0, 'on', note=61, voice=1),
                  event(30, 'on', voice=2), event(50, 'off', voice=2),
                  event(90, 'off'), event(90, 'off', note=61, voice=1)]
        result = summarize(events, [label(start=20, end=80)], sample_count=100,
                           sample_rate=96000, include_output_safety=True)
        self.assertEqual(result['output_safety']['counts'], dict(
            false_wrong_note_voice_samples=60, false_wrong_string_voice_samples=20,
            false_gap_voice_samples=60, matched_voice_samples=60, emitted_voice_samples=200,
            false_wrong_note_onsets=0, false_wrong_string_onsets=1,
            false_gap_onsets=2, matched_onsets=0, emitted_onsets=3))

    def test_output_onsets_use_half_open_labels_and_the_expected_lane_union(self):
        events = [event(0, 'on'), event(10, 'off'),
                  event(20, 'on', voice=1), event(30, 'off', voice=1),
                  event(40, 'on', note=61), event(50, 'off', note=61),
                  event(60, 'on', voice=2), event(70, 'off', voice=2),
                  event(80, 'on', voice=255), event(90, 'off', voice=255)]
        labels = [label(0, 20, 60, mask=1), label(1, 20, 40, mask=2),
                  label(2, 40, 60, mask=2), label(3, 60, 80, mask=1),
                  label(4, 80, 100, mask=0)]
        counts = summarize(events, labels, sample_count=100, sample_rate=96000,
                           include_output_safety=True)['output_safety']['counts']
        self.assertEqual(counts['false_gap_onsets'], 1)
        self.assertEqual(counts['false_wrong_note_onsets'], 1)
        self.assertEqual(counts['false_wrong_string_onsets'], 1)
        self.assertEqual(counts['matched_onsets'], 2)
        self.assertEqual(counts['emitted_onsets'], 5)

    def test_output_safety_uses_label_union_without_counting_duplicates(self):
        events = [event(0, 'on'), event(0, 'on', voice=1)]
        labels = [label(0, 0, 80, mask=1), label(1, 40, 100, mask=2),
                  label(2, 40, 60, mask=1)]
        counts = summarize(events, labels, sample_count=100, sample_rate=96000,
                           include_output_safety=True)['output_safety']['counts']
        self.assertEqual(counts['emitted_voice_samples'], 200)
        self.assertEqual(counts['matched_voice_samples'], 140)
        self.assertEqual(counts['false_wrong_string_voice_samples'], 60)
        self.assertEqual(counts['false_wrong_note_voice_samples'], 0)
        self.assertEqual(counts['false_gap_voice_samples'], 0)

    def test_unassigned_output_and_zero_mask_have_explicit_safety_semantics(self):
        labels = [label(0, 0, 50, mask=1), label(1, 50, 100, mask=0)]
        counts = summarize([event(0, 'on', voice=255)], labels, sample_count=100,
                           sample_rate=96000, include_output_safety=True)['output_safety']['counts']
        self.assertEqual(counts['false_wrong_string_voice_samples'], 50)
        self.assertEqual(counts['matched_voice_samples'], 50)
        self.assertEqual(counts['emitted_voice_samples'], 100)

    def test_silent_missing_notes_do_not_become_false_gap_outputs(self):
        result = summarize([], [label(start=20, end=80)], sample_count=100,
                           sample_rate=96000, include_output_safety=True)
        self.assertEqual(result['exact_held_samples'], 0)
        self.assertEqual(sum(result['output_safety']['counts'].values()), 0)

    def test_invalid_pairing_suppresses_output_safety(self):
        result = summarize([event(10, 'off')], [label()], sample_count=200,
                           sample_rate=96000, include_output_safety=True)
        self.assertFalse(result['output_safety']['valid'])
        self.assertIsNone(result['output_safety']['counts'])

    def test_four_singleton_labels_measure_one_simultaneous_group_without_changing_legacy(self):
        labels = [label(i, mask=1 << i) for i in range(4)]
        events = ([event(10, 'on', voice=i) for i in range(4)]
                  + [event(50, 'off'), event(50, 'on')]
                  + [event(150, 'off', voice=i) for i in range(4)])
        legacy = summarize(events, labels, sample_count=200, sample_rate=96000,
                           include_output_safety=True)
        result = summarize(events, labels, sample_count=200, sample_rate=96000,
                           include_output_safety=True, include_group_coverage=True)
        groups = result.pop('simultaneous_group_coverage')
        self.assertEqual(result, legacy)
        self.assertEqual(legacy['exact_held_samples'], 0)
        self.assertEqual(groups['annotated_group_samples'], 100)
        self.assertEqual(groups['exact_group_held_samples'], 100)
        self.assertEqual(groups['by_string_count'], {'4': dict(
            groups=1, annotated_group_samples=100, exact_group_held_samples=100)})
        row = groups['groups'][0]
        self.assertEqual(row['source_label_indices'], [0, 1, 2, 3])
        self.assertEqual(row['exact_group_hold_segments'], 1)
        self.assertEqual(row['longest_exact_group_hold_samples'], 100)
        self.assertEqual(row['note_ons_inside_group'], 1)

    def test_group_coverage_excludes_extra_and_unassigned_lanes(self):
        events = [event(0, 'on'), event(0, 'on', voice=1),
                  event(30, 'on', voice=2), event(40, 'off', voice=2),
                  event(60, 'on', voice=255), event(70, 'off', voice=255),
                  event(150, 'off'), event(150, 'off', voice=1)]
        result = summarize(events, [label(), label(1, mask=2)],
                           sample_count=200, sample_rate=96000, include_group_coverage=True)
        row = result['simultaneous_group_coverage']['groups'][0]
        self.assertEqual(row['exact_group_held_samples'], 80)
        self.assertEqual(row['unmatched_group_samples'], 20)
        self.assertEqual(row['exact_group_hold_segments'], 3)
        self.assertEqual(row['longest_exact_group_hold_samples'], 50)

    def test_partially_overlapping_annotations_partition_groups_without_duplicate_samples(self):
        labels = [label(0, 0, 80), label(1, 40, 100, mask=2), label(2, 40, 60)]
        events = [event(0, 'on'), event(40, 'on', voice=1),
                  event(80, 'off'), event(100, 'off', voice=1)]
        result = summarize(events, labels, sample_count=120, sample_rate=96000,
                           include_group_coverage=True)['simultaneous_group_coverage']
        self.assertEqual([(row['start_sample'], row['end_sample'], row['string_mask'],
                           row['source_label_indices']) for row in result['groups']],
                         [(0, 40, 1, [0]), (40, 60, 3, [0, 1, 2]),
                          (60, 80, 3, [0, 1]), (80, 100, 2, [1])])
        self.assertEqual(result['annotated_group_samples'], 100)
        self.assertEqual(result['exact_group_held_samples'], 100)
        self.assertEqual(result['by_string_count'], {
            '1': dict(groups=2, annotated_group_samples=60, exact_group_held_samples=60),
            '2': dict(groups=2, annotated_group_samples=40, exact_group_held_samples=40)})

    def test_zero_mask_leaves_simultaneous_string_membership_unmeasured(self):
        for labels, measured in (([label(0, 0, 100, mask=0)], 0),
                                 ([label(0, 0, 100), label(1, 20, 80, mask=0)], 40)):
            with self.subTest(labels=labels):
                result = summarize([event(0, 'on')], labels,
                    sample_count=120, sample_rate=96000,
                    include_group_coverage=True)['simultaneous_group_coverage']
                self.assertTrue(result['valid'])
                self.assertEqual(result['annotated_group_samples'], measured)
                self.assertEqual(result['exact_group_held_samples'], measured)
                self.assertEqual(result['unmeasured_group_samples'], 100 - measured)
                self.assertNotIn('0', result['by_string_count'])
                for row in result['groups']:
                    if not row['string_membership_measured']:
                        self.assertIsNone(row['exact_group_held_samples'])
                        self.assertIsNone(row['unmatched_group_samples'])
                        self.assertIsNone(row['longest_exact_group_hold_samples'])

    def test_different_pitch_group_samples_overlap_and_are_not_unique_audio_duration(self):
        labels = [label(0, 0, 100), label(1, 0, 100, note=64, mask=2)]
        result = summarize([event(0, 'on'), event(0, 'on', note=64, voice=1)], labels,
            sample_count=120, sample_rate=96000,
            include_group_coverage=True)['simultaneous_group_coverage']
        self.assertEqual(result['annotated_group_samples'], 200)
        self.assertEqual(result['exact_group_held_samples'], 200)
        self.assertEqual([row['midi_note'] for row in result['groups']], [60, 64])

    def test_invalid_pairing_suppresses_group_coverage(self):
        result = summarize([event(10, 'off')], [label()], sample_count=200,
                           sample_rate=96000, include_group_coverage=True)
        groups = result['simultaneous_group_coverage']
        self.assertFalse(groups['valid'])
        self.assertIsNone(groups['groups'])
        self.assertIsNone(groups['exact_group_held_samples'])
        self.assertIsNone(groups['by_string_count'])


if __name__ == '__main__':
    unittest.main()
