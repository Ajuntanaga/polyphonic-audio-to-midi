import unittest
import numpy as np
from tools.paired_harmonic_measurement import paired_measurement


class PairedMeasurementContracts(unittest.TestCase):
    def fixture(self):
        rate = 8000
        f = 440 * 2 ** ((52 - 69) / 12)
        amplitudes = np.array([1, .2, .15, .1, .08, .05])
        t = np.arange(1280) / rate
        samples = sum(a * np.sin(2*np.pi*f*h*t) for h, a in enumerate(amplitudes, 1))
        rows = [dict(sample=str(i), independent_phase_valid='1', independent_phase_cents='0',
                     **{f'corrected_harmonic_energy_{h}': str(a*a) for h, a in enumerate(amplitudes, 1)}) for i in (0, 640)]
        return rate, samples, rows, amplitudes**2 / sum(amplitudes**2)

    def test_known_harmonics_share_scale_and_boundaries(self):
        rate, samples, rows, expected = self.fixture()
        outside = dict(rows[0], sample='1280', independent_phase_valid='0')
        result = paired_measurement(samples, rate, 0, rows + [outside])
        self.assertTrue(result['eligible'])
        self.assertEqual([h['ticks'] for h in result['halves']], [1, 1])
        # Finite 80ms Hann windows have small cross-harmonic leakage.
        for h in result['halves']:
            np.testing.assert_allclose(h['shares']['spectral_exact'], expected, atol=1e-4)
            np.testing.assert_allclose(h['shares']['spectral_peak'], expected, atol=1e-4)
            np.testing.assert_allclose(h['shares']['runtime'], expected, atol=1e-12)
        quieter = paired_measurement(samples * .1, rate, 0, rows)
        np.testing.assert_allclose(quieter['halves'][0]['shares']['spectral_peak'], result['halves'][0]['shares']['spectral_peak'])

    def test_missing_phase_zero_energy_and_incomplete_window(self):
        rate, samples, rows, _ = self.fixture()
        rows[0]['independent_phase_valid'] = '0'
        result = paired_measurement(samples, rate, 0, rows)
        self.assertFalse(result['eligible'])
        self.assertNotIn('power', result['halves'][0])
        self.assertFalse(paired_measurement(samples, rate, 0, [])['eligible'])
        rows[0]['independent_phase_valid'] = '1'
        rows[0]['corrected_harmonic_energy_1'] = '0'
        self.assertFalse(paired_measurement(samples, rate, 0, rows)['eligible'])
        with self.assertRaises(ValueError):
            paired_measurement(samples[:-1], rate, 0, rows)
        rows[0]['corrected_harmonic_energy_1'] = 'nan'
        with self.assertRaises(ValueError):
            paired_measurement(samples, rate, 0, rows)
