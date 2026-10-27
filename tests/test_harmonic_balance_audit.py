import unittest

import numpy as np
from scipy.signal import lfilter

from tools.harmonic_balance_audit import (
    correlation_power, measure_clip, summarize_isolated, score_existing_fit,
)


class HarmonicBalanceTests(unittest.TestCase):
    def test_isolated_powers_keep_dc_coloring_and_are_gain_invariant(self):
        rate, center = 16000, 82.40688923
        times = np.arange(2 * rate) / rate
        frequencies = center * np.arange(1, 4) * np.exp2(np.asarray([-23, -19, -16]) / 1200)
        powers = np.asarray([0.8, 0.18, 0.02])
        signal = sum(np.sqrt(p) * np.cos(2 * np.pi * hz * times + i * 0.7)
                     for i, (p, hz) in enumerate(zip(powers, frequencies)))
        measured = measure_clip(signal, rate, center, rate // 4, 2 * rate)
        quiet = measure_clip(signal * 0.01, rate, center, rate // 4, 2 * rate)
        phase = 2 * np.pi * frequencies / rate
        dc_power = np.abs((1 - np.exp(-1j * phase)) /
                          (1 - np.exp(-2 * np.pi * 15 / rate) * np.exp(-1j * phase))) ** 2
        expected = powers * dc_power
        expected /= expected.sum()
        np.testing.assert_allclose(measured[0]['profile'], expected, atol=2e-5)
        np.testing.assert_allclose(measured[0]['profile'], quiet[0]['profile'], atol=1e-9)
        self.assertAlmostEqual(measured[0]['fundamental_cents'], -23, places=2)

    def test_correlation_inverse_handles_decay_without_undoing_input_filter(self):
        rate = 12000
        t = np.arange(3 * rate) / rate
        frequencies = np.asarray([-1.2, -2.1, -3.8])
        source_power = np.asarray([0.7, 0.2, 0.1])
        growth = -0.4
        coefficients = []
        decay = np.exp(-1 / (0.04 * rate))
        for hz, power in zip(frequencies, source_power):
            basis = np.exp((growth + 2j * np.pi * hz) * t)
            filtered = lfilter([1 - decay], [1, -decay], np.sqrt(power) * basis)
            coefficients.append(np.vdot(basis[rate:], filtered[rate:]) / np.vdot(basis[rate:], basis[rate:]))
        np.testing.assert_allclose(correlation_power(coefficients, frequencies, rate, growth),
                                   source_power, atol=1e-10)

    def test_heldout_recordings_cannot_change_training_profiles(self):
        clips = [{'clip': f'{string}-{p}', 'string': string, 'pass': p,
                  'frames': [{'profile': profile, 'power': profile}]}
                 for string, profile in enumerate(([0.9, 0.09, 0.01], [0.2, 0.7, 0.1]))
                 for p in (1, 2, 3)]
        baseline = summarize_isolated(clips)
        clips[-1]['frames'][0] = {'profile': [0.01, 0.01, 0.98], 'power': [0.01, 0.01, 0.98]}
        changed = summarize_isolated(clips)
        self.assertEqual(baseline['prototypes'], changed['prototypes'])
        self.assertEqual(baseline['bands']['3']['matched_attacks'], 4)

    def test_fitted_pair_power_recovers_each_strings_filtered_profile(self):
        rate, center = 4000, 82.40688923
        times = np.arange(4 * rate) / rate
        sources = [{'string': 0, 'partial_cents': [0, 4, 0]},
                   {'string': 1, 'partial_cents': [0, 1, 4]}]
        profiles = {'0': [0.95, 0.05, 0], '1': [0.3, 0.7, 0]}
        cents, growth = [-38, -14], [-0.4, -0.2]
        signal = np.zeros((3, len(times)), dtype=complex)
        decay = np.exp(-1 / (0.04 * rate))
        for i, source in enumerate(sources):
            for h in range(2):
                frequency = (h + 1) * center * (2 ** ((cents[i] + source['partial_cents'][h]) / 1200) - 1)
                raw = np.sqrt(profiles[str(i)][h]) * np.exp(
                    (growth[i] + 2j * np.pi * frequency) * times + 0.3j * (i + h))
                signal[h] += lfilter([1 - decay], [1, -decay], raw)
        indices = np.arange(rate, len(times), 40)
        model = {'mask': 3, 'fit_family': 'gain_drift', 'independent_cross_band_support': True,
                 'test_prediction_loss': 0, 'members': [{'string': i, 'cents_at_start': cents[i],
                    'growth_per_second': growth[i]} for i in range(2)]}
        rows = score_existing_fit(times[indices] + 100, signal[:, indices], center, sources,
                                  200, rate, [model], profiles, 3)
        for i, member in enumerate(rows[0]['members']):
            np.testing.assert_allclose(member['training_profile'], profiles[str(i)], atol=1e-9)
            np.testing.assert_allclose(member['test_profile'], profiles[str(i)], atol=1e-9)


if __name__ == '__main__':
    unittest.main()
