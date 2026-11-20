import unittest
from tools.portable_runtime_harmonic_identity import summarize_trace, eligible_evaluation
from tests.test_portable_short_window_identity import rows


def tick(sample, energy):
    return {'sample': str(sample), **{f'corrected_harmonic_energy_{h}': str(v) for h, v in enumerate(energy, 1)}}


class RuntimeEnergyContracts(unittest.TestCase):
    def test_exact_half_open_windows_and_no_floor(self):
        data = [tick(99, [0]*6), tick(100, [1, 2, 3, 4, 5, 6]),
                tick(180, [2, 4, 6, 8, 10, 12]), tick(260, [0]*6)]
        result = summarize_trace(data, 100, 1000)
        self.assertTrue(result['eligible'])
        self.assertEqual(result['ticks_per_half'], [1, 1])
        self.assertAlmostEqual(sum(result['features']['shape']), 0)
        data[1]['corrected_harmonic_energy_6'] = '0'
        result = summarize_trace(data, 100, 1000)
        self.assertFalse(result['eligible'])
        self.assertNotIn('features', result)
        self.assertEqual(result['zero_ticks_per_harmonic'][-1], 1)

    def test_missing_and_invalid_energy(self):
        self.assertFalse(summarize_trace([], 100, 1000)['eligible'])
        for bad in ('nan', '-1', 'inf'):
            row = tick(100, [1]*6)
            row['corrected_harmonic_energy_1'] = bad
            with self.assertRaises(ValueError):
                summarize_trace([row], 100, 1000)

    def test_all_takes_retained_and_missing_training_class_abstains(self):
        data = rows()
        for row in data:
            row['runtime'] = {'eligible': True, 'features': row['features']}
        result = eligible_evaluation(data, [0, 1])
        self.assertEqual((result['correct'], result['total']), (8, 8))
        for row in data:
            if row['string'] == 1:
                row['runtime']['eligible'] = False
        result = eligible_evaluation(data, [0, 1])
        self.assertEqual(result['total'], 8)
        self.assertEqual(sum(f['abstained'] for f in result['folds']), 8)
        self.assertEqual([f['total'] for f in result['folds']], [2, 2, 4])

    def test_heldout_values_do_not_change_training(self):
        data = rows()
        for row in data:
            row['runtime'] = {'eligible': True, 'features': row['features']}
        before = eligible_evaluation(data, [0, 1])['folds'][2]
        for row in data:
            if row['pass'] == 3:
                row['runtime']['features']['shape'] = [1000, -1000]
        after = eligible_evaluation(data, [0, 1])['folds'][2]
        self.assertEqual(before['training_center'], after['training_center'])
        self.assertEqual(before['training_scale'], after['training_scale'])
