import math
import unittest

from tools.spectral_sparsity_attack import ninos2, peak_candidates, decode, fit_threshold


def rows(values):
    return [{'feature': v, 'available_sample': (i + 1) * 10, 'padded_samples': 0}
            for i, v in enumerate(values)]


def candidate(frame, strength):
    return {'frame': frame, 'strength': strength, 'feature': strength,
            'available_sample': (frame + 1) * 10, 'padded_samples': 0}


def fixture(candidates, insertions=(5,), deadlines=(35,)):
    return {'candidates': candidates, 'geometry': {
        'insertions': list(insertions), 'markers': list(insertions),
        'deadlines': list(deadlines), 'sample_rate': 100, 'samples': 100}}


class FeatureContracts(unittest.TestCase):
    def test_zero_has_no_feature(self):
        self.assertEqual(ninos2([0] * 10), 0)

    def test_dense_reaches_energy_bound(self):
        self.assertAlmostEqual(ninos2([1] * 16, 1), 4 * math.log(2))

    def test_one_bin_is_sparse(self):
        self.assertAlmostEqual(ninos2([0] * 15 + [1], 1), 0)

    def test_highest_bins_excluded(self):
        self.assertEqual(ninos2([1] * 19 + [100], .95),
                         ninos2([1] * 19 + [10000], .95))

    def test_invalid_feature_input(self):
        for values in ([], [0], [-1, 2, 3], [math.nan, 1, 2], [math.inf, 1, 2]):
            with self.assertRaises(ValueError):
                ninos2(values)


class CausalContracts(unittest.TestCase):
    def test_silence_cannot_trigger_even_at_zero(self):
        self.assertEqual(decode(peak_candidates(rows([0] * 20), 3, 10), 0, 2), [])

    def test_peak_and_mean_only_read_past(self):
        a = peak_candidates(rows([0, 1, 3, 1]), 2, 3)
        b = peak_candidates(rows([0, 1, 3, 1, 1000, 0]), 2, 3)
        self.assertEqual(a, [r for r in b if r['available_sample'] <= 40])
        self.assertEqual(a[0]['strength'], .75)
        self.assertEqual(a[1]['strength'], 2)

    def test_refractory_is_strict(self):
        events = decode([candidate(0, 1), candidate(2, 1), candidate(3, 1)], 1, 2)
        self.assertEqual([e['available_sample'] for e in events], [10, 40])

    def test_emitted_clock_is_not_backdated(self):
        c = candidate(5, 1)
        c['padded_samples'] = 3
        event = decode([c], 1, 0)[0]
        self.assertEqual(event['available_sample'], 60)
        self.assertEqual(event['nominal_sample'], 60)
        self.assertEqual(event['padded_samples'], 3)

    def test_threshold_cannot_look_at_future_candidate(self):
        a = [candidate(0, 1), candidate(2, 2)]
        b = a + [candidate(4, 10)]
        self.assertEqual(decode(a, 1, 1), decode(b, 1, 1)[:2])

    def test_nonfinite_or_reversed_rows_rejected(self):
        for data in (rows([math.nan]), rows([-1]), list(reversed(rows([1, 2])))):
            with self.assertRaises(ValueError):
                peak_candidates(data, 1, 2)


class CalibrationContracts(unittest.TestCase):
    def test_removes_late_false_and_keeps_attack(self):
        train = [fixture([candidate(1, 4), candidate(5, 1)])]
        result = fit_threshold(train, 0)
        self.assertTrue(result['calibration_pass'])
        self.assertEqual(result['selected_threshold'], math.nextafter(1, math.inf))

    def test_no_operating_point_does_not_fall_back(self):
        train = [fixture([candidate(1, 1), candidate(5, 4)])]
        result = fit_threshold(train, 0)
        self.assertFalse(result['calibration_pass'])
        self.assertIsNone(result['selected_threshold'])

    def test_all_training_fixtures_must_pass(self):
        train = [fixture([candidate(1, 4), candidate(5, 1)]),
                 fixture([candidate(1, .5)])]
        self.assertFalse(fit_threshold(train, 0)['calibration_pass'])

    def test_empty_no_cue_cannot_fit(self):
        self.assertFalse(fit_threshold([fixture([])], 0)['calibration_pass'])

    def test_deadline_uses_availability(self):
        self.assertFalse(fit_threshold([fixture([candidate(3, 4)])], 0)['calibration_pass'])

    def test_two_copies_both_required(self):
        a = fixture([candidate(1, 4), candidate(6, 4)], (5, 50), (35, 80))
        self.assertTrue(fit_threshold([a], 0)['calibration_pass'])

    def test_regimes_cover_inclusive_equal_strength(self):
        result = fit_threshold([fixture([candidate(1, 1), candidate(5, 1)])], 0)
        self.assertFalse(result['calibration_pass'])
        self.assertEqual(result['threshold_regimes_evaluated'], 2)


if __name__ == '__main__':
    unittest.main()
