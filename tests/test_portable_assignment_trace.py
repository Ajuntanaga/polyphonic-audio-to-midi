import tempfile
from pathlib import Path
import unittest

from tools.portable_assignment_trace import (assignment_summary, digest, profile_addition_summary,
                                             read_rows, trace_bounds, verify_inputs)


class PortableAssignmentTraceTests(unittest.TestCase):
    def test_mask_counts_preserve_missing_and_extra_strings(self):
        row = dict(note='52', sample='1023', expected_note='1', expected_mask='40',
                   observed='1', valid='1', complete_calibration='1', playable='63',
                   prior_primary='3', dp_primary='3', final_primary='3', final_mask='24',
                   rendered_mask='24', midi_mask='24', group_after='24', primary_only_render='0',
                   use_posterior='1', posterior_observation_available='1', posterior_updated='1',
                   profile_fit_observed='1', profile_uses_long_memory='0')
        result = assignment_summary([row], note=52, start=1000, end=1100, expected_mask=40)
        self.assertEqual(result['exact_rendered_rows'], 0)
        self.assertEqual(result['missing_expected_lane_rows'], {'3': 0, '5': 1})
        self.assertEqual(result['extra_lane_rows']['4'], 1)
        self.assertEqual(result['profile_first_pass']['state'], 'not measured')
        row['expected_mask'] = '24'
        with self.assertRaisesRegex(ValueError, 'label identity'):
            assignment_summary([row], note=52, start=1000, end=1100, expected_mask=40)

    def test_profile_rejections_keep_uncomputed_errors_distinct_from_zero(self):
        rows = [dict(profile_first_pass_reasons='2,2,2,8,2,1,2,2',
                     profile_first_pass_alpha='-1,-1,-1,0.99,-1,-1,-1,-1',
                     profile_first_pass_errors='-1,-1,-1,-1,-1,-1,-1,-1'),
                dict(profile_first_pass_reasons='2,2,2,12,2,1,2,2',
                     profile_first_pass_alpha='-1,-1,-1,0.5,-1,-1,-1,-1',
                     profile_first_pass_errors='-1,-1,-1,0,-1,-1,-1,-1')]
        result = profile_addition_summary(rows)
        self.assertEqual(result['captured_rows'], 2)
        rejected = result['by_string']['3']['retained_component_too_small']
        self.assertEqual(rejected['alpha_min'], 0.99)
        self.assertNotIn('candidate_error_min', rejected)
        accepted = result['by_string']['3']['accepted']
        self.assertEqual(accepted['candidate_error_min'], 0)
        self.assertEqual(accepted['candidate_error_measured_rows'], 1)
        rows[0]['profile_first_pass_reasons'] = '2,2,2,99,2,1,2,2'
        with self.assertRaisesRegex(ValueError, 'Unknown profile'):
            profile_addition_summary(rows)
        del rows[0]['profile_first_pass_errors']
        with self.assertRaisesRegex(ValueError, 'Incomplete profile'):
            profile_addition_summary(rows)

    def test_changed_recording_is_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ('physical-middle.wav', 'physical-middle.tsv', 'calibration.m3cb', 'templates.tsv')
            for name in names:
                (root / name).write_text(name)
            manifest = {'files': {name: {'sha256': digest(root / name)} for name in names}}
            verify_inputs(root, manifest, 'physical-middle')
            (root / 'physical-middle.wav').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Input identity failed'):
                verify_inputs(root, manifest, 'physical-middle')

    def test_trace_covers_late_labels_without_silent_truncation(self):
        labels = [{'start_sample': 531840, 'end_sample': 752640},
                  {'start_sample': 4379520, 'end_sample': 4600320}]
        start, end = trace_bounds(labels, 7478400, 96000)
        self.assertLess(start * 96000, 531840)
        self.assertGreater(end * 96000, 4600320)
        labels[1]['end_sample'] = 7478400
        with self.assertRaisesRegex(ValueError, 'frame limit'):
            trace_bounds(labels, 7478400, 96000)

    def test_outcome_schema_comment_does_not_become_the_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'outcome.tsv'
            path.write_text('# m3_candidate_outcome_v2\nsample\tcandidates\n63\t52:4\n')
            self.assertEqual(read_rows(path), [{'sample': '63', 'candidates': '52:4'}])


if __name__ == '__main__':
    unittest.main()
