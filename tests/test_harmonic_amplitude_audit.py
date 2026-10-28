import copy
import unittest

import numpy as np

from tools.coupled_harmonic_fit import current_energy_audit
from tools.harmonic_amplitude_audit import audit_window, refresh_gain
from tools.harmonic_drift_fit import _basis


class HarmonicAmplitudeAuditTests(unittest.TestCase):
    def test_gain_refresh_recovers_four_sources_and_is_scale_invariant(self):
        rng = np.random.default_rng(43)
        columns = rng.normal(size=(120, 4)) + 1j * rng.normal(size=(120, 4))
        expected = np.array([0.7, 1.2, 1.6, 0.9])
        target = columns @ expected
        for scale in (0.01, 1, 10):
            result = refresh_gain(columns * scale, target * scale)
            self.assertTrue(result['valid'])
            np.testing.assert_allclose(result['gain'], expected, atol=1e-10)

    def test_bounds_and_unidentifiable_members_cannot_qualify(self):
        columns = np.eye(4, dtype=complex)
        bounded = refresh_gain(columns, np.array([0.1, 1, 1, 1]))
        self.assertFalse(bounded['valid'])
        self.assertTrue(bounded['at_boundary'])
        self.assertFalse(refresh_gain(np.ones((20, 2)), np.ones(20))['valid'])
        columns[:, 0] = 0
        self.assertFalse(refresh_gain(columns, np.ones(4))['valid'])

    def fixture(self):
        times = np.arange(301) * 0.01
        center = 82.40688923
        cents = np.array([-35, -20, -8])
        growth = np.zeros(3)
        profiles = np.array([[0.8, 0.6, 0.2], [0.1, 0.4, 0.7], [0.1, 0.0, 0.1]])
        sources = [{'string': i, 'fret': 8 - 4 * i, 'cents': cents[i],
                    'partial_cents': [0, 2 * i, 3 * i], 'profile': profiles[:, i].tolist(),
                    'valid_mask': 7} for i in range(3)]
        coefficients = np.sqrt(profiles) * np.exp(0.7j * np.arange(3))[None, :]
        columns = np.array([_basis(times, center, sources, cents, cents, growth, times[-1], h)
                            * coefficients[h] for h in range(3)])
        signal = columns.sum(axis=2)
        signal[:, 100:] *= 0.6
        model = {'mask': 7, 'fit_family': 'coupled_profile', 'converged': True,
                 'members': [{'string': i, 'cents': cents[i], 'growth_per_second': 0} for i in range(3)],
                 'coefficients_real': (coefficients.real * 0.8).tolist(),
                 'coefficients_imaginary': (coefficients.imag * 0.8).tolist()}
        return times, signal, center, sources, model, columns

    def inspect(self, times, signal, center, sources, model):
        original = current_energy_audit(times, signal, center, sources, 200, 3, [model], True, True)
        result = audit_window(times + 10, signal, center, 40, sources, 200, 3,
                              [model], original, True, True)
        return original, result

    def test_recent_training_improves_frozen_prediction_without_future_leakage(self):
        times, signal, center, sources, model, _ = self.fixture()
        saved = copy.deepcopy(model)
        original, result = self.inspect(times, signal, center, sources, model)
        refreshed = result['models'][0]
        self.assertGreater(original['models'][0]['test_prediction_loss'], 0.1)
        self.assertLess(refreshed['test_prediction_loss'], 1e-20)
        np.testing.assert_allclose(refreshed['amplitude_refresh']['gain'], [0.75] * 3, atol=1e-10)
        changed = signal.copy()
        changed[:, 200:] *= 3 * np.exp(0.5j)
        _, future = self.inspect(times, changed, center, sources, model)
        self.assertEqual(refreshed['amplitude_refresh'], future['models'][0]['amplitude_refresh'])
        self.assertEqual(model, saved)

    def test_refresh_cannot_invent_a_third_string_or_survive_silence(self):
        times, _, center, sources, model, columns = self.fixture()
        pair = columns[:, :, 1:].sum(axis=2) * 0.8
        _, result = self.inspect(times, pair, center, sources, model)
        self.assertFalse(result['models'][0]['one_band_per_member_profile_support'])
        sounding = columns.sum(axis=2) * 0.8
        sounding[:, 200:] = 0
        _, stopped = self.inspect(times, sounding, center, sources, model)
        self.assertFalse(stopped['models'][0]['one_band_per_member_profile_support'])
        self.assertFalse(stopped['models'][0]['independent_cross_band_support'])

    def test_reopened_audio_must_reproduce_the_saved_frozen_audit(self):
        times, signal, center, sources, model, _ = self.fixture()
        original = current_energy_audit(times, signal, center, sources, 200, 3, [model], True, True)
        changed = signal.copy()
        changed[1, 200:] *= 0.5
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            audit_window(times, changed, center, 40, sources, 200, 3,
                         [model], original, True, True)
        altered = copy.deepcopy(original)
        altered['models'][0]['test_prediction_loss'] += 0.01
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            audit_window(times, signal, center, 40, sources, 200, 3,
                         [model], altered, True, True)


if __name__ == '__main__':
    unittest.main()
