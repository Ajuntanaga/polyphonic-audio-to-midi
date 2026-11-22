"""Tiny generated signals locally; encoder execution and fitting stay on GitHub."""
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tools.harmonic_spectral_patches import (SPECTRAL_PATCHES, HarmonicPatchFeatures,
    fit_patch_normalization)
from tools.shared_harmonic_learning import HarmonicFeatures, SETTINGS


class SpectralPatchFeatureTests(unittest.TestCase):
    def setUp(self):
        self.extractor = HarmonicPatchFeatures()

    def test_layout_and_frequency_grid(self):
        extractor = self.extractor
        self.assertEqual(len(extractor.coordinate_names), 302)
        self.assertEqual(len(set(extractor.names)), 53*302)
        self.assertEqual(extractor.names[0], 'note32:w4096:h0.5:offset-2:relative_db')
        self.assertEqual(extractor.names[-1], 'note84:w16384:rms_db')
        self.assertEqual(extractor.frequency.shape, (53, 6, 25))
        offsets = 12*np.log2(extractor.frequency[0, 1]/extractor.frequency[0, 1, 12])
        np.testing.assert_allclose(offsets, np.arange(-12, 13)/6, atol=2e-14, rtol=0)

    def test_original_centers_and_rms_are_bit_identical(self):
        time = np.arange(16384)/SETTINGS['sample_rate']
        random = np.random.default_rng(20261122).normal(0, .05, 16384)
        for signal in (.1*np.sin(2*np.pi*164.813778*time), random):
            actual = self.extractor(signal).reshape(53, 2, 151)
            original = HarmonicFeatures()(signal).reshape(53, 2, 31)
            self.assertEqual(actual.dtype, np.float32)
            self.assertTrue(np.isfinite(actual).all())
            np.testing.assert_array_equal(actual[..., np.arange(6)*25+12],
                                          original[..., np.arange(6)*5+2])
            np.testing.assert_array_equal(actual[..., 150], original[..., 30])

    def test_short_branch_ignores_older_context(self):
        signal = np.random.default_rng(23).normal(0, .05, 16384)
        original = self.extractor(signal).reshape(53, 2, 151)
        changed = signal.copy()
        changed[:-4096] += .3
        actual = self.extractor(changed).reshape(53, 2, 151)
        np.testing.assert_array_equal(actual[:, 0], original[:, 0])
        self.assertFalse(np.array_equal(actual[:, 1], original[:, 1]))

    def test_relative_gain_and_silence(self):
        signal = np.random.default_rng(42).normal(0, .05, 16384)
        original = self.extractor(signal).reshape(53, 2, 151)
        louder = self.extractor(2*signal).reshape(53, 2, 151)
        np.testing.assert_array_equal(louder[..., :150], original[..., :150])
        np.testing.assert_allclose(louder[..., 150]-original[..., 150],
                                   20*np.log10(2), atol=3e-6, rtol=0)
        silence = self.extractor(np.zeros(16384)).reshape(53, 2, 151)
        np.testing.assert_array_equal(silence[..., :150], -80)
        np.testing.assert_array_equal(silence[..., 150], -120)

    def test_invalid_context_is_rejected(self):
        for signal in (np.zeros(16383), np.zeros((1, 16384)),
                       np.full(16384, np.nan), np.full(16384, np.inf)):
            with self.assertRaises(ValueError):
                self.extractor(signal)

    def test_chunked_training_moments_and_constant_coordinates(self):
        # 4,187 candidate rows exercise two full chunks and one partial chunk.
        features = np.random.default_rng(17).normal(size=(79, 53*302)).astype(np.float32)
        rows = features.reshape(-1, 302)
        rows[:, 4] = 3
        mean, scale = fit_patch_normalization(features)
        reference = rows.astype(np.float64)
        expected_scale = reference.std(axis=0)
        expected_scale[expected_scale < 1e-12] = 1
        np.testing.assert_allclose(mean, reference.mean(axis=0).astype(np.float32), atol=1e-8, rtol=0)
        np.testing.assert_array_equal(scale, expected_scale.astype(np.float32))
        self.assertEqual(mean.dtype, np.float32)
        self.assertEqual(scale[4], 1)
        with self.assertRaises(ValueError):
            fit_patch_normalization(np.empty((0, 53*302), np.float32))


@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true', 'Model execution stays on GitHub')
class SpectralPatchModelTests(unittest.TestCase):
    def setUp(self):
        import torch
        from tools.harmonic_context_learning import SETWISE_PARAMS
        torch.set_num_threads(1)
        torch.manual_seed(SETWISE_PARAMS['seed'])

    def test_shared_encoder_preserves_patch_and_rms_layout(self):
        import torch
        from tools.harmonic_spectral_patches import make_patch_network
        network = make_patch_network()
        self.assertEqual(sum(p.numel() for p in network.parameters()), 31825)
        with torch.no_grad():
            for conv in (network.shape[0], network.shape[2]):
                conv.weight.zero_()
                conv.bias.zero_()
            network.shape[0].weight[0, 0, 1] = 1
            network.shape[0].weight[1, 1, 1] = 1
            for channel in range(4):
                network.shape[2].weight[channel, channel % 2, 1] = 1
        windows = torch.arange(1, 1+2*3*2*151, dtype=torch.float32).reshape(2, 3, 2, 151)
        values = windows.reshape(2, 3, 302).transpose(1, 2)
        encoded = network.encode(values).transpose(1, 2)
        expected = []
        for harmonic in range(6):
            patch = windows[..., harmonic*25:(harmonic+1)*25]
            expected.append(patch[:, :, [0, 1, 0, 1], :].reshape(2, 3, 100))
        expected.append(windows[..., 150])
        torch.testing.assert_close(encoded, torch.cat(expected, dim=2), rtol=0, atol=0)

    def test_gradients_and_saved_model_reproduce_activity(self):
        import torch
        from tools import harmonic_context_learning as context
        from tools import portable_harmonic_context_learning as runner
        from tools.harmonic_spectral_patches import make_patch_network
        network = make_patch_network()
        features = np.random.default_rng(7).normal(size=(2, 53*302)).astype(np.float32)
        values = torch.from_numpy(context.normalized_context(features, np.zeros(302), np.ones(302), 302))
        logits = network(values)
        self.assertEqual(tuple(logits.shape), (2, 53))
        logits.square().mean().backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in network.parameters()))
        self.assertGreater(float(network.shape[0].weight.grad.abs().sum()), 0)
        model = context.HarmonicContextModel(np.zeros(302, np.float32), np.ones(302, np.float32), network.eval(), .6)
        expected = model.activity(features)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'model.pt'
            runner.save_model(path, model, HarmonicPatchFeatures(), context.SETWISE_PARAMS)
            saved = torch.load(path, map_location='cpu', weights_only=True)
            self.assertEqual(saved['spectral_patch_parameters'], SPECTRAL_PATCHES)
            self.assertEqual(saved['feature_count'], 302)
            self.assertEqual(saved['coordinate_names'], HarmonicPatchFeatures().coordinate_names)
            restored_network = make_patch_network()
            restored_network.load_state_dict(saved['state_dict'])
            restored = context.HarmonicContextModel(saved['mean'].numpy(), saved['scale'].numpy(),
                                                    restored_network, saved['cutoff'])
            np.testing.assert_array_equal(restored.activity(features), expected)

    def test_tiny_frozen_fit_and_input_contract(self):
        from tools.harmonic_context_learning import SETWISE_PARAMS
        from tools import portable_harmonic_context_learning as runner
        features = np.random.default_rng(15).normal(size=(3, 53*302)).astype(np.float32)
        truth = np.zeros((3, 53), bool)
        truth[0, [3, 15]] = True
        truth[1, [21, 32, 44]] = True
        model, report = runner.fit_model(features, truth, SETWISE_PARAMS, spectral_patches=SPECTRAL_PATCHES)
        self.assertEqual(report['optimizer_steps'], 80)
        self.assertEqual(report['epochs'], 80)
        self.assertEqual(report['feature_storage_dtype'], 'float32')
        self.assertEqual(report['parameter_count'], 31825)
        self.assertTrue(report['normalized_batch_storage'])
        self.assertTrue(np.isfinite(report['loss_curve']).all())
        self.assertTrue(np.isfinite(model.activity(features)).all())
        for invalid in (features.astype(np.float64), features[:, :53*62]):
            with self.assertRaises(ValueError):
                runner.fit_model(invalid, truth, SETWISE_PARAMS, spectral_patches=SPECTRAL_PATCHES)


if __name__ == '__main__':
    unittest.main()
