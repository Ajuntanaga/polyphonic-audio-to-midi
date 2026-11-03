import json
import unittest

import numpy as np

from tools.partial_motion_evidence import (
    condition_mixture_tracks, summarize_motion, trajectories, validate_join,
)


class PartialMotionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.times = np.arange(401) / 100
        self.center = 100
        h = np.arange(1, 4)[:, None]
        # Identical fractional frequency motion on three measured bands.
        self.signal = np.exp(-0.4 * self.times) * np.exp(
            2j * np.pi * h * (1.2 * self.times + 0.03 * self.times ** 3))

    def test_known_chirp_uses_demodulation_center_and_harmonic_number(self):
        result = trajectories(self.times, self.signal, self.center)
        expected_hz = 1.2 + 0.03 * np.diff(self.times ** 3) / np.diff(self.times)
        expected = 1200 * np.log2(1 + expected_hz / self.center)
        np.testing.assert_allclose(result['cents'], np.tile(expected, (3, 1)), atol=1e-10)
        measured = summarize_motion(self.times, self.signal, self.center)
        for pair in measured['pairs']:
            self.assertAlmostEqual(pair['frequency_motion_correlation'], 1)
        self.assertIsNone(measured['string_mask_decision'])
        self.assertEqual(measured['source_dominant_reference'], 'not measured')

    def test_gain_and_later_audio_cannot_change_prior_measurements(self):
        original = trajectories(self.times, self.signal, self.center)
        scaled = trajectories(self.times, self.signal * 0.017, self.center)
        changed_signal = self.signal.copy()
        changed_signal[:, 250:] *= 500 * np.exp(1j)
        changed = trajectories(self.times, changed_signal, self.center)
        for key in ('valid', 'cents', 'envelope_rate', 'motion_valid', 'frequency_motion'):
            np.testing.assert_allclose(original[key], scaled[key], atol=1e-8)
            np.testing.assert_allclose(original[key][:, :248], changed[key][:, :248], atol=0)

    def test_weak_missing_and_large_phase_steps_are_unavailable(self):
        signal = self.signal.copy()
        signal[2] *= 1e-7
        signal[0, 100] = np.nan
        signal[1, 200:] *= np.exp(0.99j * np.pi)
        result = trajectories(self.times, signal, self.center)
        self.assertFalse(result['valid'][2].any())
        self.assertFalse(result['valid'][0, 99:101].any())
        self.assertFalse(result['motion_valid'][0, 98:101].any())
        self.assertFalse(result['valid'][1, 199])
        report = summarize_motion(self.times, signal, self.center)
        self.assertIsNone(report['pairs'][1]['frequency_motion_correlation'])
        json.dumps(report, allow_nan=False)

    def test_silence_and_constant_decay_do_not_create_correlation(self):
        silence = summarize_motion(self.times, np.zeros_like(self.signal), self.center)
        self.assertEqual(silence['valid_increment_counts'], [0, 0, 0])
        self.assertTrue(all(p['frequency_motion_correlation'] is None for p in silence['pairs']))
        decay = summarize_motion(self.times, self.signal, self.center)
        self.assertTrue(all(p['envelope_motion_correlation'] is None for p in decay['pairs']))

    def test_missing_time_span_is_not_interpreted_as_smooth_motion(self):
        keep = np.r_[0:100, 150:401]
        result = trajectories(self.times[keep], self.signal[:, keep], self.center)
        self.assertFalse(result['valid'][:, 99].any())
        self.assertFalse(result['motion_valid'][:, 98:100].any())
        self.assertTrue(result['valid'][:, 100].all())
        prefix = trajectories(self.times[:100], self.signal[:, :100], self.center)
        np.testing.assert_equal(prefix['cents'], result['cents'][:, :99])

    def test_join_requires_recording_calibration_settings_and_exact_tick(self):
        identity = dict(audio_sha256='audio', calibration_sha256='cal', sample_rate=96000,
                        sample_origin=0, decision_sample=1024, note=40, settings_sha256='settings')
        self.assertTrue(validate_join(identity, identity)['joinable'])
        self.assertFalse(validate_join({}, {})['joinable'])
        for key in identity:
            other = dict(identity)
            other.pop(key)
            self.assertIn(key, validate_join(identity, other)['missing'])
            other[key] = 'different'
            self.assertIn(key, validate_join(identity, other)['mismatched'])

    def test_conditioning_is_causal_gain_linear_and_resets_missing_observations(self):
        def filtered(times, signal):
            return condition_mixture_tracks(times, signal, observation_period=0.01)
        original = filtered(self.times, self.signal)
        np.testing.assert_allclose(filtered(self.times, 0.017 * self.signal),
                                   0.017 * original, atol=1e-14)
        np.testing.assert_equal(filtered(self.times[:200], self.signal[:, :200]),
                                original[:, :200])
        damaged = self.signal.copy()
        damaged[:, 200] = np.nan
        after_missing = filtered(self.times, damaged)
        self.assertTrue(np.isnan(after_missing[:, 200]).all())
        np.testing.assert_allclose(after_missing[:, 201:],
                                   filtered(self.times[201:], self.signal[:, 201:]),
                                   rtol=0, atol=1e-14)
        keep = np.r_[0:100, 150:401]
        after_gap = filtered(self.times[keep], self.signal[:, keep])
        np.testing.assert_equal(after_gap[:, 100:],
                                filtered(self.times[150:], self.signal[:, 150:]))

    def test_conditioning_reduces_known_leakage_without_erasing_slow_frequency(self):
        # A constant-frequency source plus a small fast contaminant is not a
        # second moving string. Differentiating its raw phase exaggerates it.
        times = np.arange(3000) / 750
        slow = np.exp(2j * np.pi * 0.37 * times)
        signal = (slow + 0.02 * np.exp(2j * np.pi * 82.4 * times))[None, :]
        clean = condition_mixture_tracks(times, signal, observation_period=1 / 750)
        raw = trajectories(times, signal, 82.4)
        conditioned = trajectories(times, clean, 82.4)
        steady = times[2:] > 1
        self.assertLess(np.std(conditioned['frequency_motion'][0, steady]),
                        np.std(raw['frequency_motion'][0, steady]) / 30)
        expected = 1200 * np.log2(1 + 0.37 / 82.4)
        self.assertAlmostEqual(float(np.mean(conditioned['cents'][0, times[1:] > 1])),
                               expected, places=2)


if __name__ == '__main__':
    unittest.main()
