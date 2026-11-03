import json
import unittest

import numpy as np

from tools.partial_motion_evidence import (
    condition_mixture_tracks, phase_window_trajectories, summarize_motion,
    summarize_phase_windows, summarize_reference_quality, trajectories, validate_join,
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

    def test_phase_window_chirp_has_correct_time_scale_and_harmonic_normalization(self):
        # Quadratic phase has a linear frequency trajectory. Its exact OLS slope
        # time is available even when the observation clock is irregular.
        times = np.arange(1001) / 250
        times[1:-1:2] += 0.0005
        h = np.arange(1, 7)[:, None]
        signal = np.exp(-0.3 * times + 2j * np.pi * h * (0.5 * times + 0.1 * times ** 2))
        result = phase_window_trajectories(times, signal, 82.4)
        expected = 1200 * np.log2(1 + (0.5 + 0.2 * result['estimate_times']) / 82.4)
        np.testing.assert_allclose(result['cents'], np.tile(expected, (6, 1)), atol=1e-10)
        np.testing.assert_allclose(result['envelope_rate'], -0.3, atol=1e-12)
        self.assertTrue(result['valid'].all())
        self.assertTrue(np.all(result['estimate_times'] < result['increment_times']))
        self.assertTrue(np.all(result['increment_times'] >= 0.160))

    def test_phase_window_is_causal_gain_invariant_and_never_resets_at_labels(self):
        result = phase_window_trajectories(self.times, self.signal, self.center)
        scaled = phase_window_trajectories(self.times, 0.017 * self.signal, self.center)
        prefix = phase_window_trajectories(self.times[:250], self.signal[:, :250], self.center)
        changed = self.signal.copy()
        changed[:, 250:] *= 500 * np.exp(1j)
        suffix = phase_window_trajectories(self.times, changed, self.center)
        for key in ('valid', 'cents', 'envelope_rate', 'motion_valid', 'frequency_motion'):
            np.testing.assert_allclose(result[key], scaled[key], atol=1e-8)
            np.testing.assert_equal(result[key][:, :prefix[key].shape[1]], prefix[key])
            np.testing.assert_equal(suffix[key][:, :prefix[key].shape[1]], prefix[key])
        before = {key: value.copy() if isinstance(value, np.ndarray) else value
                  for key, value in result.items()}
        summary = summarize_phase_windows(result, 0.5, 3.5)
        summarize_phase_windows(result, 1.5, 2.5)
        for key in result:
            np.testing.assert_equal(result[key], before[key])
        self.assertEqual(summary, summarize_phase_windows(result, 0.5, 3.5))
        self.assertIsNone(summary['string_mask_decision'])
        json.dumps(summary, allow_nan=False)

    def test_phase_windows_reject_missing_weak_jumping_and_gapped_spans(self):
        damaged = self.signal.copy()
        damaged[0, 100] = np.nan
        damaged[1, 200:] *= np.exp(0.99j * np.pi)
        damaged[2] *= 1e-7
        result = phase_window_trajectories(self.times, damaged, self.center)
        around_missing = ((result['increment_times'] >= 1)
                          & (result['increment_times'] <= 1.16))
        around_jump = ((result['increment_times'] >= 2)
                       & (result['increment_times'] <= 2.16))
        self.assertTrue(around_missing.any())
        self.assertFalse(result['valid'][0, around_missing].any())
        self.assertFalse(result['valid'][1, around_jump].any())
        self.assertFalse(result['valid'][2].any())
        keep = np.r_[0:100, 150:401]
        gapped = phase_window_trajectories(self.times[keep], self.signal[:, keep], self.center)
        at_gap = (gapped['increment_times'] >= 1.5) & (gapped['increment_times'] < 1.66)
        self.assertTrue(at_gap.any())
        self.assertFalse(gapped['valid'][:, at_gap].any())
        self.assertTrue(gapped['valid'][:, -1].all())

    def test_phase_windows_silence_short_input_and_constant_decay_abstain(self):
        silence = phase_window_trajectories(self.times, np.zeros_like(self.signal), self.center)
        self.assertFalse(silence['valid'].any())
        self.assertFalse(silence['motion_valid'].any())
        short = phase_window_trajectories(self.times[:5], self.signal[:, :5], self.center)
        self.assertEqual(short['cents'].shape, (3, 0))
        summary = summarize_phase_windows(short, 0, 3)
        self.assertTrue(all(p['frequency_motion_correlation'] is None for p in summary['pairs']))
        decay = np.exp(-0.4 * self.times)[None, :] * np.ones((3, 1))
        track = phase_window_trajectories(self.times, decay, self.center)
        report = summarize_phase_windows(track, 0, 4)
        self.assertTrue(all(p['frequency_motion_correlation'] is None for p in report['pairs']))
        self.assertTrue(all(p['envelope_motion_correlation'] is None for p in report['pairs']))

    def test_phase_window_reduces_known_single_source_fast_error(self):
        times = np.arange(3000) / 750
        slow = np.exp(2j * np.pi * 0.37 * times)
        contaminated = (slow + 0.02 * np.exp(2j * np.pi * 82.4 * times))[None, :]
        conditioned = condition_mixture_tracks(times, contaminated, observation_period=1 / 750)
        raw = trajectories(times, conditioned, 82.4)
        fitted = phase_window_trajectories(times, conditioned, 82.4)
        self.assertLess(np.std(fitted['frequency_motion'][0, fitted['motion_times'] > 1]),
                        np.std(raw['frequency_motion'][0, raw['motion_times'] > 1]) / 30)
        expected = 1200 * np.log2(1 + 0.37 / 82.4)
        self.assertAlmostEqual(float(np.mean(fitted['cents'][0, fitted['increment_times'] > 1])),
                               expected, places=2)

    def test_rejection_reasons_explain_each_invalid_increment_and_window(self):
        damaged = self.signal.copy()
        damaged[0, 100] = np.nan
        damaged[1, 200:] *= np.exp(0.99j * np.pi)
        damaged[2] *= 1e-7
        keep = np.r_[0:300, 350:401]
        times, signal = self.times[keep], damaged[:, keep]
        increments = trajectories(times, signal, self.center)
        windows = phase_window_trajectories(times, signal, self.center)
        for track in (increments, windows):
            union = np.logical_or.reduce(list(track['rejection_reasons'].values()))
            np.testing.assert_equal(union, ~track['valid'])
        reasons = increments['rejection_reasons']
        self.assertEqual(int(reasons['nonfinite_sample'][0].sum()), 2)
        self.assertEqual(int(reasons['phase_step'][1].sum()), 1)
        self.assertTrue(reasons['weak_or_zero_amplitude'][2].all())
        self.assertEqual(reasons['observation_gap'].sum(axis=1).tolist(), [1, 1, 1])
        # A negative inferred absolute frequency is a distinct causal failure.
        negative = np.exp(-0.1j * np.arange(10))[None, :]
        track = trajectories(np.arange(10) / 100, negative, 0.1)
        self.assertTrue(track['rejection_reasons']['invalid_frequency'].all())
        self.assertFalse(track['valid'].any())

    def test_quality_separates_disabled_bands_silence_and_empty_spans(self):
        signal = self.signal.copy()
        signal[2] = 0
        increments = trajectories(self.times, signal, self.center)
        windows = phase_window_trajectories(self.times, signal, self.center)
        quality = summarize_reference_quality(increments, windows, [True, True, False], 0, 4)
        disabled = quality['bands'][2]
        self.assertEqual(disabled['rejected_window_counts'], {'disabled_band': disabled['windows']})
        self.assertIsNone(disabled['minimum_endpoint_amplitude_ratio'])
        self.assertIsNone(quality['string_mask_decision'])
        self.assertEqual(quality['source_dominant_reference'], 'not measured')
        weak = summarize_reference_quality(increments, windows, [True] * 3, 0, 4)['bands'][2]
        self.assertEqual(weak['rejected_window_counts']['weak_or_zero_amplitude'], weak['windows'])
        empty = summarize_reference_quality(increments, windows, [True] * 3, 10, 11)
        self.assertTrue(all(b['valid_window_fraction'] is None for b in empty['bands']))
        json.dumps([quality, empty], allow_nan=False)

    def test_quality_is_prefix_and_gain_invariant_with_labels_used_only_for_scoring(self):
        def quality(times, signal):
            return summarize_reference_quality(
                trajectories(times, signal, self.center),
                phase_window_trajectories(times, signal, self.center), [True] * 3, 0.5, 2)
        full = quality(self.times, self.signal)
        prefix = quality(self.times[:220], self.signal[:, :220])
        self.assertEqual(full, prefix)
        scaled = quality(self.times, self.signal * 0.017)
        for original, changed in zip(full['bands'], scaled['bands']):
            for key in ('valid_increments', 'valid_windows', 'rejected_increment_counts',
                        'rejected_window_counts'):
                self.assertEqual(original[key], changed[key])
            for key in ('minimum_endpoint_amplitude_ratio', 'phase_fit_rms_radians'):
                np.testing.assert_allclose(list(original[key].values()), list(changed[key].values()), atol=1e-12)

    def test_phase_fit_residual_detects_nonlinearity_but_never_vetoes_it(self):
        h = np.arange(1, 4)[:, None]
        linear = np.exp(2j * np.pi * h * self.times)
        curved = np.exp(2j * np.pi * h * (self.times + 0.1 * self.times ** 2))
        straight = phase_window_trajectories(self.times, linear, self.center)
        bending = phase_window_trajectories(self.times, curved, self.center)
        self.assertTrue(straight['valid'].all() and bending['valid'].all())
        self.assertLess(float(straight['phase_fit_rms_radians'].max()), 1e-12)
        self.assertGreater(float(bending['phase_fit_rms_radians'].min()), 0.001)
        self.assertIsNone(summarize_reference_quality(
            trajectories(self.times, curved, self.center), bending,
            [True] * 3, 0, 4)['string_mask_decision'])


if __name__ == '__main__':
    unittest.main()
