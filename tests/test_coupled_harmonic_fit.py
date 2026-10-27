import json
import unittest

import numpy as np
from scipy.signal import lfilter

from tools.coupled_harmonic_fit import current_energy_audit, fit_mask


def sources(count=3):
    partials = ([0, 4.5, 0], [0, 1.1, 4.7], [0, 6.7, 7], [0, 10, 12])
    return [{'string': i, 'partial_cents': list(partials[i])} for i in range(count)]


def observed(times, center, templates, cents, growth, profiles, rate=8000):
    clock = np.arange(round((times[-1] + 1.1) * rate)) / rate
    indices = np.rint((times + 1) * rate).astype(int)
    signal = np.zeros((3, len(indices)), dtype=complex)
    decay = np.exp(-1 / (0.04 * rate))
    for i, source in enumerate(templates):
        for h in range(3):
            frequency = (h + 1) * center * (2 ** ((cents[i] + source['partial_cents'][h]) / 1200) - 1)
            raw = np.sqrt(profiles[str(source['string'])][h]) * np.exp(
                (growth[i] + 2j * np.pi * frequency) * clock + 0.7j * (i + h))
            signal[h] += lfilter([1 - decay], [1, -decay], raw)[indices]
    return signal


def seed(cents, growth):
    return {'members': [{'cents_at_start': c, 'growth_per_second': g} for c, g in zip(cents, growth)]}


class CoupledHarmonicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.times = np.arange(301) * 0.01
        cls.templates = sources()
        cls.profiles = {'0': [0.99424, 0.005745, 0.000015],
                        '1': [0.737, 0.2615, 0.0015], '2': [0.1146, 0.8077, 0.0777]}
        cls.cents, cls.growth = [-35, -20, -8], [-0.3, -0.4, -0.2]
        cls.center = 82.40688923
        cls.signal = observed(cls.times, cls.center, cls.templates, cls.cents, cls.growth, cls.profiles)
        cls.seeds = [seed([-19, -36, -7], [-0.4, -0.3, -0.2])]
        cls.fitted = fit_mask(cls.times, cls.signal, cls.center, cls.templates, 200, 8000,
                              cls.profiles, 3, cls.seeds)

    def test_joint_fit_resolves_swapped_string_seeds_and_natural_decay(self):
        self.assertTrue(self.fitted['converged'])
        self.assertLess(self.fitted['test_prediction_loss'], 1e-8)
        np.testing.assert_allclose([m['cents'] for m in self.fitted['members']], self.cents, atol=1e-3)
        json.dumps(self.fitted, allow_nan=False)

    def test_test_audio_cannot_change_learned_parameters(self):
        changed = self.signal.copy()
        changed[:, 200:] *= 3 * np.exp(0.5j)
        fitted = fit_mask(self.times, changed, self.center, self.templates, 200, 8000,
                          self.profiles, 3, self.seeds)
        for before, after in zip(self.fitted['members'], fitted['members']):
            for key in ('cents', 'growth_per_second', 'fitted_profile', 'profile_change_db'):
                self.assertEqual(before[key], after[key])
        self.assertGreater(fitted['test_prediction_loss'], 0.1)

    def test_pair_cannot_gain_a_supported_missing_member_from_profile_prior(self):
        signal = observed(self.times, self.center, self.templates[1:], self.cents[1:],
                          self.growth[1:], self.profiles)
        result = fit_mask(self.times, signal, self.center, self.templates, 200, 8000,
                          self.profiles, 3, [seed(self.cents, self.growth)])
        missing = next(m for m in result['members'] if m['string'] == 0)
        self.assertEqual(missing['supported_harmonics'], 0)

    def test_four_strings_can_be_fitted_without_changing_the_source_limit(self):
        templates = sources(4)
        profiles = {**self.profiles, '3': [0.4, 0.45, 0.15]}
        cents, growth = [-39, -15, 11, 34], [-0.3, -0.1, -0.2, -0.35]
        center = self.center * 2
        signal = observed(self.times, center, templates, cents, growth, profiles)
        result = fit_mask(self.times, signal, center, templates, 200, 8000, profiles, 7,
                          [seed(np.asarray(cents) + [1, -1, 1, -1], growth)])
        self.assertLess(result['test_prediction_loss'], 1e-8)
        np.testing.assert_allclose([m['cents'] for m in result['members']], cents, atol=1e-3)

    def test_current_energy_confidence_preserves_scale_and_refuses_silence(self):
        def inspect(signal, model):
            return current_energy_audit(self.times, signal, self.center, self.templates,
                                        200, 3, [model], True, True)
        baseline = inspect(self.signal, self.fitted)
        quiet_model = {**self.fitted,
                       'coefficients_real': (np.asarray(self.fitted['coefficients_real']) * 0.01).tolist(),
                       'coefficients_imaginary': (np.asarray(self.fitted['coefficients_imaginary']) * 0.01).tolist()}
        reduced = inspect(self.signal * 0.01, quiet_model)
        first, second = baseline['models'][0], reduced['models'][0]
        self.assertAlmostEqual(first['test_prediction_loss'], second['test_prediction_loss'], places=9)
        self.assertEqual(first['supported_harmonics_per_member'], second['supported_harmonics_per_member'])
        silent = self.signal.copy()
        silent[:, 200:] = 0
        stopped = inspect(silent, self.fitted)
        self.assertTrue(all(v > 0 for v in stopped['test_scale_squared']))
        self.assertFalse(stopped['models'][0]['one_band_per_member_profile_support'])
        self.assertFalse(stopped['models'][0]['independent_cross_band_support'])
        json.dumps(stopped, allow_nan=False)

    def test_one_band_only_cannot_supply_string_profile_evidence(self):
        result = current_energy_audit(self.times, self.signal, self.center, self.templates,
                                      200, 1, [self.fitted], True, True)
        self.assertFalse(result['models'][0]['one_band_per_member_profile_support'])
        self.assertFalse(result['models'][0]['independent_cross_band_support'])


if __name__ == '__main__':
    unittest.main()
