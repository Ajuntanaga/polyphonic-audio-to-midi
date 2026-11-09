import tempfile
from pathlib import Path
import unittest

from tools.portable_assignment_trace import assignment_summary, digest, read_rows, trace_bounds, verify_inputs


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
        row['expected_mask'] = '24'
        with self.assertRaisesRegex(ValueError, 'label identity'):
            assignment_summary([row], note=52, start=1000, end=1100, expected_mask=40)

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
