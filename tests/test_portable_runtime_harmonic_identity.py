import unittest
import numpy as np
from tools.harmonic_cell_unmix import response_matrix
from tools.portable_runtime_harmonic_identity import summarize_complex_trace
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


class ComplexTraceContracts(unittest.TestCase):
    def test_input_referred_shape_and_invalid_phase_abstention(self):
        rate = 96000
        frequencies = 440 * 2**((52-69)/12) * np.arange(1, 7)
        decay = np.exp(-1/(rate*.04))
        z = np.exp(-2j*np.pi*frequencies/rate)
        gain = np.abs((1-z)/(1-np.exp(-2*np.pi*15/rate)*z))**2
        powers = np.array([1, .01, .003, .002, .001, .0001])
        coefficients = np.zeros(12)
        coefficients[::2] = np.sqrt(2*powers*gain)
        observed = response_matrix(frequencies, frequencies, rate, decay) @ coefficients
        rows = []
        for sample in (100, 7780):
            row = dict(sample=str(sample), complex_valid='1', complex_decay=str(decay), phase_valid='1', phase_cents='0', independent_phase_valid='1', independent_phase_cents='0')
            for i in range(6):
                row.update({f'complex_hz_{i+1}': str(frequencies[i]), f'complex_real_{i+1}': str(observed[2*i]), f'complex_imag_{i+1}': str(observed[2*i+1])})
            rows.append(row)
        for mode in ('nominal', 'runtime_phase', 'independent_phase'):
            summary = summarize_complex_trace(rows, 100, rate, mode)
            self.assertTrue(summary['eligible'])
            expected = np.log10(powers); expected -= expected.mean()
            np.testing.assert_allclose(summary['features']['shape'], expected, atol=1e-10)
        rows[0]['phase_valid'] = '0'
        summary = summarize_complex_trace(rows, 100, rate, 'runtime_phase')
        self.assertFalse(summary['eligible'])
        self.assertEqual(summary['rejected_ticks'], 1)
        self.assertEqual(summary['ticks_per_half'], [1, 1])

        self.assertTrue(summarize_complex_trace(rows, 100, rate, 'independent_phase')['eligible'])
        rows[0]['independent_phase_valid'] = '0'
        independent = summarize_complex_trace(rows, 100, rate, 'independent_phase')
        self.assertFalse(independent['eligible'])
        self.assertEqual(independent['rejected_ticks'], 1)
        self.assertEqual(independent['ticks_per_half'], [1, 1])
