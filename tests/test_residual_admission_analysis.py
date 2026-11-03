import csv
import io
import unittest

from tools.residual_admission_analysis import FIELDS, EXTENDED_FIELDS, analyze_stream


def observation(**changes):
    row = dict.fromkeys(EXTENDED_FIELDS, 0)
    row.update(sample=40000, tick=1008, note=49, base_count=2,
               used_mask=3, free_mask=4, any_label=1, expected_note=1,
               expected_mask=4, base_valid=1, added_valid=1,
               base_residual=.4, added_residual=.1, residual_gain=.3,
               independent_energy=.2, score_ratio=1.5, fund_ratio=.8,
               direct=1, local=1, calibration_similarity=.9,
               calibration_string=2, base_notes='40,45')
    row.update(changes)
    return row


def analyze(*rows, fields=EXTENDED_FIELDS, **capture_changes):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t', extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    stream.seek(0)
    capture = dict(rows=len(rows), truncated=False, decimation=16)
    capture.update(capture_changes)
    return analyze_stream(stream, capture)


class ResidualAdmissionAnalysisTests(unittest.TestCase):
    def test_old_capture_is_explicitly_supported_without_inventing_lane_costs(self):
        result = analyze(observation(), fields=FIELDS)
        self.assertFalse(result['lane_costs_available'])
        self.assertEqual(result['persistence_screen']['native_lane_policies'], [])
        with self.assertRaises(ValueError):
            analyze(observation(), fields=EXTENDED_FIELDS[:-1])

    def test_persistence_requires_adjacent_samples_and_the_same_best_string(self):
        def row(tick, **changes):
            data = dict(tick=tick, sample=tick * 64, free_mask=12,
                        lane_fixed_context=1, lane_selected_count=2,
                        lane_available_mask=12, lane_cost_2=0., lane_cost_3=12.)
            data.update(changes)
            return observation(**data)
        result = analyze(row(1008), row(1024), row(1040, expected_mask=8),
                         row(1056, lane_cost_2=20., lane_cost_3=0.),
                         row(1088), row(1104), row(1120, any_label=0, expected_note=0))
        screen = result['persistence_screen']
        counts = screen['pitch_observations']['3']
        self.assertEqual(counts['expected_free_string'], 2)
        self.assertEqual(counts['extra_gap'], 1)
        policy = next(p for p in screen['native_lane_policies']
                      if p['sampled_observations_required'] == 3 and p['margin_floor'] == 8.)
        self.assertEqual(policy['observations']['expected_free_string'], 1)
        self.assertEqual(policy['observations']['extra_gap'], 1)
        self.assertEqual(policy['wrong_string'], 1)
        strict = next(p for p in screen['native_lane_policies']
                      if p['sampled_observations_required'] == 3 and p['margin_floor'] == 32.)
        self.assertEqual(sum(strict['observations'].values()), 0)

    def test_tied_costs_do_not_claim_a_best_string_and_sole_choices_are_labeled(self):
        result = analyze(
            observation(free_mask=12, lane_fixed_context=1, lane_selected_count=2,
                        lane_available_mask=12),
            observation(tick=1024, lane_fixed_context=1, lane_selected_count=2,
                        lane_available_mask=4, lane_cost_2=-12.))
        policy = result['persistence_screen']['native_lane_policies'][0]
        self.assertEqual(policy['observations']['expected_free_string'], 1)
        self.assertEqual(policy['sole_available_string'], 1)
        for strict in result['persistence_screen']['native_lane_policies']:
            if strict['margin_floor'] > 0.:
                self.assertEqual(sum(strict['observations'].values()), 0)

    def test_unavailable_labeled_strings_are_not_native_ranking_errors(self):
        result = analyze(
            observation(expected_mask=8, lane_fixed_context=1, lane_selected_count=2,
                        lane_available_mask=4, lane_cost_2=-12.),
            observation(tick=1024, free_mask=12, expected_mask=8,
                        lane_fixed_context=1, lane_selected_count=2,
                        lane_available_mask=4, lane_cost_2=-12.))
        policy = result['persistence_screen']['native_lane_policies'][0]
        self.assertEqual(policy['observations']['expected_occupied_string'], 1)
        self.assertEqual(policy['observations']['expected_free_string'], 1)
        self.assertEqual(policy['wrong_string'], 0)
        self.assertEqual(policy['labeled_string_unavailable'], 2)

    def test_invalid_lane_evidence_fails_closed(self):
        for changes in (dict(lane_available_mask=4), dict(lane_cost_2=1.),
                        dict(lane_fixed_context=2),
                        dict(lane_fixed_context=1, lane_selected_count=1),
                        dict(lane_fixed_context=1, lane_selected_count=2, lane_available_mask=1),
                        dict(lane_cost_2=float('nan'))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                analyze(observation(**changes))

    def test_pitch_and_string_evidence_remain_separate(self):
        result = analyze(
            observation(),
            observation(tick=1024, sample=41000, expected_mask=8),
            observation(tick=1040, sample=42000, expected_mask=0),
            observation(tick=1056, sample=43000, expected_note=0),
            observation(tick=1072, sample=44000, any_label=0, expected_note=0))
        self.assertEqual(result['totals']['eligible'], 5)
        policy = result['policies'][-1]
        self.assertEqual(policy['expected_pitch_samples'], 3)
        self.assertEqual(policy['false_pitch_samples'], 2)
        self.assertEqual(policy['calibrated_wrong_string'], 1)
        self.assertEqual(policy['sole_free_string']['expected_free_string'], 1)
        self.assertFalse(result['production_changed'])

    def test_ambiguous_and_already_emitted_candidates_are_not_promoted(self):
        result = analyze(
            observation(shared_fundamental=1),
            observation(tick=1024, fundamental_overlap=.99),
            observation(tick=1040, already_emitted=1),
            observation(tick=1056, base_count=1, base_notes='40'),
            observation(tick=1072, added_valid=0))
        self.assertEqual(result['totals']['harmonic_ambiguity'], 2)
        self.assertEqual(result['totals']['already_emitted'], 1)
        self.assertEqual(result['totals']['fewer_than_two_base_pitches'], 1)
        self.assertEqual(result['totals']['invalid_fit'], 1)
        self.assertTrue(all(p['expected_pitch_samples'] == 0 for p in result['policies']))

    def test_both_gain_and_independent_energy_are_required(self):
        result = analyze(observation(added_residual=.399, residual_gain=.001,
                                     independent_energy=.0001))
        self.assertEqual(result['policies'][0]['expected_pitch_samples'], 1)
        self.assertEqual(result['policies'][-1]['expected_pitch_samples'], 0)

    def test_invalid_captures_fail_closed(self):
        for capture in (dict(truncated=True), dict(decimation=8), dict(rows=2)):
            with self.subTest(capture=capture), self.assertRaises(ValueError):
                analyze(observation(), **capture)

    def test_invalid_or_inconsistent_evidence_is_rejected(self):
        for change in (dict(free_mask=3), dict(tick=1009), dict(note=128),
                       dict(base_notes='40,40'), dict(residual_gain=.2),
                       dict(independent_energy=float('nan'))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                analyze(observation(**change))
        with self.assertRaises(ValueError):
            analyze(observation(), observation())


if __name__ == '__main__':
    unittest.main()
