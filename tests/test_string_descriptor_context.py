import copy
import csv
import gzip
import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from tools.string_descriptor_context import (
    analyze, annotations, compare, matched_geometry, run, summarize_segments,
)


def row(sample):
    return dict(sample=str(sample), tick=str((sample + 1) // 64), note='36',
                expected_note='1', expected_mask='1', observed='1', valid='0',
                fixed_context='0', complete_calibration='1',
                posterior_observation_available='1', playable='3',
                reserved_coasting='0', reserved_extras='0',
                lane_terms='0:0:-256:0:0:0:0,0:0:256:0:0:0:0,' +
                           ','.join(['0:0:0:0:0:0:0'] * 6),
                posterior_detuning_valid_mask='3',
                posterior_detuning_log_likelihood='-2,2,0,0,0,0,0,0',
                assignment_cents='0', phase_valid='1', learned_cents='0,8,0,0,0,0,0,0',
                posterior_log_likelihood='-9,7,0,0,0,0,0,0',
                isolated='1', beat_valid='0', fine_valid='0', selected_count='1')


def metadata(rows):
    return dict(grid_stride_samples=64, sample_rate=1000, sample_count=1024,
                sampled_frames=16, trace_rows=len(rows), annotations=[
                    dict(index=0, start=0, end=1024, note=36, mask=1)])


class DescriptorContextTests(unittest.TestCase):
    def test_annotation_age_and_missing_rows_never_become_neutral_evidence(self):
        rows = [row(s) for s in (63, 127, 383)]
        result = analyze(rows, metadata(rows), [(36, 0, 1)])
        self.assertEqual(result['coverage']['measured_pairs'], 2)
        self.assertEqual(result['coverage']['missing_assignment_row'], 10)
        self.assertEqual([s['age'] for s in result['segments']],
                         ['attack_0_100ms', 'settled_350ms_plus'])
        for segment in result['segments']:
            c = segment['counts']
            self.assertEqual(c['descriptor_sum'], -20)
            self.assertEqual(c['descriptor_reverses_correct_other_terms'], 1)
        # valid=0 (joint allocation failed) does not invalidate observed margins.

    def test_reserved_lanes_and_unavailable_observations_are_excluded(self):
        rows = [row(s) for s in (383, 447, 511)]
        rows[0]['reserved_extras'] = '2'
        rows[1]['posterior_observation_available'] = '0'
        rows[2]['complete_calibration'] = '0'
        result = analyze(rows, metadata(rows), [(36, 0, 1)])
        self.assertEqual(result['segments'], [])
        self.assertEqual(result['coverage']['reserved_or_infeasible_pair'], 1)
        self.assertEqual(result['coverage']['likelihood_unavailable'], 2)

    def test_contradictory_context_label_clock_or_row_count_fails(self):
        for field, value in [('fixed_context', '1'), ('observed', '0'),
                             ('expected_mask', '2'), ('tick', '99')]:
            r = row(383); r[field] = value
            with self.assertRaises(ValueError):
                analyze([r], metadata([r]), [(36, 0, 1)])
        with self.assertRaises(ValueError):
            analyze([row(383), row(383)], metadata([row(383)]), [(36, 0, 1)])
        with self.assertRaises(ValueError):
            analyze([row(383)], metadata([]), [(36, 0, 1)])

    def test_geometry_excludes_single_feasible_lane_and_unmatched_pitch(self):
        a = dict(annotations=[dict(note=n, mask=1) for n in (32, 36, 40)])
        b = dict(annotations=[dict(note=n, mask=1) for n in (32, 36, 41)])
        self.assertEqual(matched_geometry([a, b], 24), [(36, 0, 1)])

    def test_episodes_keep_overlapping_labels_together_and_ambiguous_age_out(self):
        rows = [row(383)]
        m = metadata(rows)
        m['annotations'][0]['end'] = 640
        m['annotations'] += [dict(index=1, start=128, end=800, note=36, mask=1),
                             dict(index=2, start=800, end=1000, note=36, mask=1)]
        self.assertEqual([a['episode'] for a in annotations(m)], [0, 0, 1])
        result = analyze(rows, m, [(36, 0, 1)])
        self.assertEqual(result['segments'], [])
        self.assertGreater(result['coverage']['overlapping_same_pitch_targets_excluded'], 0)

    def test_long_segments_do_not_dominate_equal_segment_summary(self):
        segments = [dict(episode=0, counts=dict(pairs=1, descriptor_negative=1, descriptor_sum=-5)),
                    dict(episode=1, counts=dict(pairs=100, descriptor_negative=0, descriptor_sum=100))]
        result = summarize_segments(segments)
        self.assertEqual(result['equal_segment_descriptor_negative_percent'], 50)
        self.assertAlmostEqual(result['descriptor_negative_percent'], 100 / 101)
        self.assertEqual(result['equal_segment_descriptor_margin'], -2)

    def test_comparison_matches_geometry_and_context_without_filling_absence(self):
        base = dict(annotation=0, episode=0, note=36, lane=0, fret=4, competitor=1,
                    age='settled_350ms_plus', counts=dict(pairs=1, descriptor_negative=1,
                                                       descriptor_sum=-5))
        chord = dict(base, context='annotated_chord')
        isolated = dict(base, context='annotated_single',
                        counts=dict(pairs=10, descriptor_negative=0, descriptor_sum=20))
        other = dict(chord, note=40)
        result = compare({'ordinary': {'segments': [chord, other]},
                          'isolated-08': {'segments': [isolated]}})
        self.assertEqual(result[0]['ordinary_minus_isolated_negative_percentage_points'], 100)
        self.assertIsNone(result[1]['ordinary_minus_isolated_negative_percentage_points'])
        self.assertIsNone(result[1]['datasets']['isolated-08'])

    def test_capture_provenance_and_trace_identity_are_checked(self):
        rows = [row(383)]
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader(); writer.writerows(rows)
        raw = stream.getvalue().encode()
        source = dict(analysis=metadata(rows), provenance=dict(
            calibration_sha256='cal', settings={'max-fret': 24}, sample_rate=1000,
            trace_sha256=hashlib.sha256(raw).hexdigest(), take_identity='one'))
        report = dict(state='completed', final=True, run_id='capture', binary_sha256='binary',
                      source_files_sha256={}, datasets={name: copy.deepcopy(source)
                      for name in ('ordinary', 'isolated-08')})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'trace.gz'
            path.write_bytes(gzip.compress(raw))
            paths = {name: path for name in report['datasets']}
            result = run(paths, report)
            self.assertFalse(result['causal_overlap_measured'])
            self.assertFalse(result['held_out_gain_measured'])
            report['datasets']['isolated-08']['provenance']['calibration_sha256'] = 'other'
            with self.assertRaisesRegex(ValueError, 'incompatible calibration'):
                run(paths, report)
            report['datasets']['isolated-08']['provenance']['calibration_sha256'] = 'cal'
            report['datasets']['ordinary']['provenance']['trace_sha256'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'trace SHA-256'):
                run(paths, report)


if __name__ == '__main__':
    unittest.main()
