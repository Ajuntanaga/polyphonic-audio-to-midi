import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_portable_three_string_lock_trace import observations
from tools.portable_short_four_profile_trace import (
    CASE, CONDITIONS, DATASET, GROUP, WINDOW, chronology, run, validate_reference)


REFERENCE = Path(__file__).resolve().parents[1] / 'docs/recovery/short-four-profile-references-20261115.json'


def profile_row(sample, *, profile=True, render=True, routed=8, matched=(36,)):
    frame, row = observations(sample, fine=0, committed=8, assigned=8, routed=routed)
    frame['matched_labels'] = list(matched)
    row.update(note='53', playable='63', render_observed=str(int(render)),
               profile_fit_observed=str(int(profile)), profile_uses_long_memory='0',
               candidate_age_ticks='400', beat_valid='0')
    row['profile_first_pass_reasons'] = '6,7,8,1,3,5,2,2'
    return frame, row


class ShortFourProfileTraceTests(unittest.TestCase):
    def test_singleton_match_or_first_pass_acceptance_is_not_four_string_acquisition(self):
        a = profile_row(CASE['start_sample'] + 2)
        b = profile_row(CASE['start_sample'] + 66, routed=31, matched=(36, 37, 38, 39))
        b[1]['profile_first_pass_reasons'] = '12,7,8,1,3,5,2,2'
        result = chronology([a[1], b[1]], [a[0], b[0]], CASE)
        self.assertEqual(result['singleton_anchor']['string_mask'], 8)
        self.assertEqual(result['group']['string_mask'], 15)
        self.assertEqual(result['counts']['all_group_labels_matched'], 1)
        self.assertEqual(result['mask_histograms']['midi'], {'8': 1, '31': 1})
        self.assertNotIn('15', result['mask_histograms']['rendered'])
        self.assertEqual(result['counts']['profile_fit'], 2)
        self.assertIn('accepted is not final group', result['interpretation'])

    def test_unobserved_and_skipped_fits_do_not_invent_first_pass_evidence(self):
        pairs = [profile_row(CASE['start_sample'] + 2, profile=False),
                 profile_row(CASE['start_sample'] + 66, render=False),
                 profile_row(CASE['start_sample'] + 130)]
        pairs[2][0]['candidate_state'] = None
        pairs[2][0]['routing']['render_observed'] = 0
        result = chronology([row for _, row in pairs[:2]], [frame for frame, _ in pairs], CASE)
        self.assertEqual(result['counts']['profile_not_fit'], 1)
        self.assertEqual(result['counts']['profile_unobserved'], 2)
        self.assertEqual(result['mask_histograms']['midi']['unobserved'], 1)
        self.assertEqual(result['profile_first_addition']['captured_rows'], 0)

    def test_reference_checks_all_four_annotations_and_complete_input_provenance(self):
        reference = json.loads(REFERENCE.read_text())
        manifest = dict(source=copy.deepcopy(reference['source']), files=copy.deepcopy(reference['inputs']))
        validate_reference(reference, manifest)
        changes = [lambda r: r['case'].update(string_mask=15),
                   lambda r: r['group'].update(string_mask=7),
                   lambda r: r['replay_references']['current-on']['held_labels']['39'].update(string_mask=2),
                   lambda r: r['replay_references']['current-on'].pop('outcome_sha256'),
                   lambda r: r['source'].update(input_bundle_sha256='0'*64),
                   lambda r: r['inputs']['synthetic-four.tsv'].update(sha256='0'*64)]
        for change in changes:
            with self.subTest(change=change):
                altered = copy.deepcopy(reference)
                change(altered)
                with self.assertRaises(ValueError):
                    validate_reference(altered, manifest)

    def test_one_unchanged_replay_uses_the_singleton_anchor_and_bounded_window(self):
        reference = json.loads(REFERENCE.read_text())
        with tempfile.TemporaryDirectory() as directory, patch('tools.portable_short_four_profile_trace.capture') as mocked:
            root = Path(directory)
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(dict(source=reference['source'], files=reference['inputs'])))
            run(root/'binary', root/'corpus', manifest, REFERENCE, root/'output')
            self.assertEqual(mocked.call_count, 1)
            kwargs = mocked.call_args.kwargs
            self.assertEqual(kwargs['dataset'], DATASET)
            self.assertEqual(kwargs['conditions'], CONDITIONS)
            self.assertEqual(kwargs['cases'], (CASE,))
            self.assertEqual(kwargs['window'](CASE), WINDOW)
            self.assertIs(kwargs['diagnose'], chronology)

    def test_outside_window_frames_cannot_be_presented_as_inside_group_evidence(self):
        frame, row = profile_row(CASE['start_sample'] - 1)
        with self.assertRaisesRegex(ValueError, 'No frames'):
            chronology([row], [frame], CASE)
        with self.assertRaisesRegex(ValueError, 'singleton anchor'):
            chronology([row], [frame], dict(CASE, string_mask=GROUP['string_mask']))


if __name__ == '__main__':
    unittest.main()
