"""Synthetic phase measurements; recorded signals and model fitting stay remote."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import harmonic_phase_motion as phase
from tools import harmonic_context_learning as context
from tools import portable_harmonic_context_learning as runner


class PhaseMotionTests(unittest.TestCase):
    def setUp(self):
        self.extractor = phase.HarmonicPhaseFeatures()
        self.time = np.arange(max(phase.SETTINGS['windows']))/phase.SETTINGS['sample_rate']

    def tone(self, note=69, cents=0, initial_phase=0):
        frequency = 440*2**((note-69)/12+cents/1200)
        return np.sin(2*np.pi*frequency*self.time+initial_phase)

    def phase_values(self, signal):
        return self.extractor(signal).reshape(53, 74)[:, 62:].reshape(53, 6, 2)

    def test_complex_increment_sign_and_nominal_step_removal(self):
        step = np.array([.2, 1.3, 4.1])
        residual = np.array([-.1, .0, .3])
        values = np.exp(1j*(np.arange(3)[:, None]*(step+residual)+.7))
        np.testing.assert_allclose(phase.phase_residual(values, step), np.exp(1j*residual), atol=1e-14)
        np.testing.assert_allclose(phase.phase_residual(values*.01, step), np.exp(1j*residual), atol=1e-14)

    def test_opposed_increments_cancel_and_power_floor_goes_to_zero(self):
        self.assertAlmostEqual(phase.phase_residual(np.array([1, 1, -1]), 0), 0)
        self.assertEqual(phase.phase_residual(np.zeros(3), 0), 0)
        self.assertAlmostEqual(phase.phase_residual(np.full(3, 1e-12), 0), 2e-4)
        for values, step in ((np.ones(2), 0), (np.array([1, np.nan, 1]), 0), (np.ones(3), np.inf)):
            with self.assertRaises(ValueError):
                phase.phase_residual(values, step)

    def test_original_features_are_bit_identical_and_layout_is_explicit(self):
        signal = self.tone(cents=20)+.13*self.tone(note=57)
        actual = self.extractor(signal).reshape(53, 74)
        np.testing.assert_array_equal(actual[:, :62], self.extractor.base(signal).reshape(53, 62))
        self.assertEqual(len(self.extractor.coordinate_names), 74)
        self.assertEqual(len(set(self.extractor.names)), 53*74)
        self.assertEqual(self.extractor.coordinate_names[62:66],
                         ['w8192:hop512:h0.5:phase_real', 'w8192:hop512:h0.5:phase_imag',
                          'w8192:hop512:h1:phase_real', 'w8192:hop512:h1:phase_imag'])
        self.assertTrue(np.isfinite(actual).all())
        self.assertTrue(np.all(np.linalg.norm(actual[:, 62:].reshape(53, 6, 2), axis=-1) <= 1+1e-7))

    def test_sinusoid_detuning_and_initial_phase(self):
        for cents in (-25, 0, 25):
            frequency = 440*2**(cents/1200)
            expected = np.exp(2j*np.pi*(frequency-440)*512/96000)
            for offset in (0, 1.1):
                measured = self.phase_values(self.tone(cents=cents, initial_phase=offset))[69-32, 1]
                np.testing.assert_allclose(measured, [expected.real, expected.imag], atol=2e-5)

    def test_all_harmonic_probes_have_the_expected_phase(self):
        for index, multiplier in enumerate(phase.PHASE_MOTION['harmonic_multipliers']):
            signal = np.sin(2*np.pi*440*multiplier*self.time+.4)
            np.testing.assert_allclose(self.phase_values(signal)[69-32, index], [1, 0], atol=2e-5)

    def test_gain_silence_and_past_only_span(self):
        signal = self.tone(cents=18)
        # The occupied fundamental is above the power floor. Almost-empty
        # distant bins deliberately tend to zero and are not gain invariant.
        np.testing.assert_allclose(self.phase_values(signal)[69-32, 1],
                                   self.phase_values(.1*signal)[69-32, 1], atol=1e-6)
        np.testing.assert_array_equal(self.phase_values(np.zeros_like(signal)), np.zeros((53, 6, 2)))
        earlier_changed = signal.copy()
        earlier_changed[:-9216] = 100
        np.testing.assert_array_equal(self.phase_values(earlier_changed), self.phase_values(signal))
        for bad in (signal[:-1], np.full_like(signal, np.nan)):
            with self.assertRaises(ValueError):
                self.extractor(bad)

    def test_scaler_retains_the_new_coordinate_axis(self):
        values = np.zeros((2, 53, 74), np.float32)
        values[1, :, 73] = 2
        mean, scale = context.fit_normalization(values.reshape(2, -1), 74)
        normalized = context.normalized_context(values.reshape(2, -1), mean, scale, 74)
        self.assertEqual(normalized.shape, (2, 74, 53))
        np.testing.assert_array_equal(normalized[:, 73, :], np.tile([[-1], [1]], (1, 53)))

    def test_single_pitch_gate_uses_exact_false_and_missing_counts(self):
        truth = np.zeros((3132, 53), bool)
        truth[:, 0] = True
        probability = truth.astype(float)
        probability[:5, 0] = 0
        probability[4:17, 1] = 1
        result = phase.single_pitch_preservation(probability, truth, .5)
        self.assertTrue(result['passed'])
        self.assertEqual(result['current'], dict(examples=3132, exact_sets=3115, false_positive=13, false_negative=5))
        cases = []
        extra = probability.copy()
        extra[0, 2] = 1
        cases.append(extra)
        missing = probability.copy()
        missing[17, 0] = 0
        cases.append(missing)
        fewer_exact = probability.copy()
        fewer_exact[4, 1], fewer_exact[17, 1] = 0, 1
        cases.append(fewer_exact)
        for changed in cases:
            self.assertFalse(phase.single_pitch_preservation(changed, truth, .5)['passed'])
        self.assertFalse(phase.single_pitch_preservation(probability[:-1], truth[:-1], .5)['passed'])
        self.assertTrue(phase.single_pitch_preservation(truth.astype(float), truth, .5)['passed'])
        # The gate is specific to singleton mixtures, not silence or chords.
        mixed_truth = np.concatenate((truth, np.zeros((1, 53), bool), np.ones((1, 53), bool)))
        mixed_probability = np.concatenate((probability, np.ones((1, 53)), np.zeros((1, 53))))
        self.assertEqual(phase.single_pitch_preservation(mixed_probability, mixed_truth, .5), result)
        with self.assertRaises(ValueError):
            phase.single_pitch_preservation(probability[:, :52], truth, .5)


@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true', 'Model fitting runs on GitHub only')
class PhaseNetworkTests(unittest.TestCase):
    def test_74_coordinate_fit_and_persisted_model_roundtrip(self):
        import torch
        rng = np.random.default_rng(12)
        raw = rng.normal(size=(32, 53, 74)).astype(np.float32)
        truth = raw[:, :, -1] > .5
        features = raw.reshape(32, -1)
        params = dict(context.SETWISE_PARAMS, epochs=10)
        with patch.object(runner, 'remote_only'), redirect_stdout(io.StringIO()):
            model, fit = runner.fit_model(features, truth, params)
            self.assertEqual(fit['features_per_candidate'], 74)
            self.assertEqual(sum(p.numel() for p in model.network.parameters()), 14849)
            self.assertLess(fit['final_loss'], fit['loss_curve'][0])
            model.cutoff = .6
            probability = model.activity(features)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'model.pt'
                runner.save_model(path, model, phase.HarmonicPhaseFeatures(), params)
                saved = torch.load(path, map_location='cpu', weights_only=True)
                self.assertEqual(saved['feature_count'], 74)
                self.assertEqual(saved['phase_parameters'], phase.PHASE_MOTION)
                network = context.make_network(saved['feature_count'])
                network.load_state_dict(saved['state_dict'])
                restored = context.HarmonicContextModel(saved['mean'].numpy(), saved['scale'].numpy(), network, .6)
                np.testing.assert_array_equal(restored.activity(features), probability)
                np.testing.assert_array_equal(restored.predict_proba(features), probability >= .6)


if __name__ == '__main__':
    unittest.main()
