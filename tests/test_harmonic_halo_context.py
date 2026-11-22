"""Synthetic signals/tensors only; CPU torch execution belongs to GitHub."""
from contextlib import redirect_stdout
from importlib.util import find_spec
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import harmonic_context_learning as context
from tools import harmonic_halo_context as halo
from tools import portable_harmonic_context_learning as runner
from tools.shared_harmonic_learning import HarmonicFeatures


class HaloFeaturesTests(unittest.TestCase):
    def test_measured_central_coordinates_are_bit_identical(self):
        baseline, extended = HarmonicFeatures(), halo.HarmonicHaloFeatures()
        t = np.arange(16384)/96000
        signals = [np.zeros(16384), .05*np.sin(2*np.pi*440*t),
                   np.random.default_rng(3).normal(0, .02, 16384)]
        for signal in signals:
            old, new = baseline(signal), extended(signal)
            self.assertEqual(new.shape, (125*62,))
            np.testing.assert_array_equal(halo.central_features(new[None])[0], old)
        self.assertEqual(extended.names[36*62:89*62], baseline.names)
        self.assertEqual(extended.note_count, 125)
        self.assertLess(extended.frequency.max(), 48000)
        # Beyond-range rows are measured, not zero-filled copies of the boundary.
        measured = extended(signals[1]).reshape(125, 62)
        self.assertTrue(np.any(measured[:36] != 0))
        self.assertFalse(np.array_equal(measured[0], measured[36]))

    def test_scaler_sees_only_the_unchanged_central_training_rows(self):
        raw = np.random.default_rng(8).normal(size=(5, 125, 62)).astype(np.float32)
        expected = context.fit_normalization(raw[:, 36:89].reshape(5, -1))
        raw[:, :36] += 1e5
        raw[:, 89:] -= 1e5
        actual = context.fit_normalization(halo.central_features(raw.reshape(5, -1)))
        for a, b in zip(actual, expected):
            np.testing.assert_array_equal(a, b)
        normalized = context.normalized_context(raw.reshape(5, -1), *actual, note_count=125)
        self.assertEqual(normalized.shape, (5, 62, 125))
        np.testing.assert_allclose(normalized[:, :, 36:89].mean(axis=(0, 2)), 0, atol=1e-7)

    def test_invalid_context_is_rejected_and_empty_batch_preserved(self):
        for values in (np.zeros((1, 53*62)), np.zeros((1, 125*62-1)),
                       np.full((1, 125*62), np.nan)):
            with self.assertRaises(ValueError):
                halo.central_features(values)
        self.assertEqual(halo.central_features(np.zeros((0, 125*62))).shape, (0, 53*62))
        for kwargs in (dict(note_low=2, note_high=1), dict(note_low=0, note_high=128)):
            with self.assertRaises(ValueError):
                HarmonicFeatures(**kwargs)


@unittest.skipUnless(find_spec('torch'), 'Pinned CPU torch runs on GitHub only')
class HaloNetworkTests(unittest.TestCase):
    def test_same_parameters_and_initialization_with_valid_geometry(self):
        import torch
        torch.set_num_threads(1)
        torch.manual_seed(20261121)
        original = context.make_network()
        torch.manual_seed(20261121)
        extended = context.make_network(valid_context=True)
        self.assertEqual(sum(p.numel() for p in extended.parameters()), 14465)
        for key, value in original.state_dict().items():
            self.assertTrue(torch.equal(value, extended.state_dict()[key]))
        self.assertTrue(all(layer.padding == (0,) for layer in extended.context))
        self.assertEqual(tuple(extended(torch.zeros(2, 62, 125)).shape), (2, 53))

    def test_valid_convolutions_remove_boundary_position_signal(self):
        import torch
        torch.set_num_threads(1)
        network = context.make_network(valid_context=True)
        with torch.no_grad():
            for p in network.parameters():
                p.fill_(.01)
            constant = network(torch.ones(1, 62, 125))
            torch.testing.assert_close(constant, constant[:, :1].expand_as(constant), rtol=0, atol=0)
            # Shift the feature grid by one row: overlapping predictions agree.
            grid = torch.rand(1, 62, 126)
            a, b = network(grid[..., :-1]), network(grid[..., 1:])
            torch.testing.assert_close(a[:, 1:], b[:, :-1], rtol=1e-6, atol=1e-6)

    def test_residual_crops_keep_target_alignment(self):
        import torch
        network = context.make_network(valid_context=True)
        with torch.no_grad():
            for p in network.parameters():
                p.zero_()
            network.input.weight[0, 0, 0] = 1
            network.output.weight[0, 0, 0] = 1
            values = torch.zeros(1, 62, 125)
            values[0, 0, 36] = 2
            values[0, 0, 88] = 3
            values[0, 0, 35] = 99
            values[0, 0, 89] = 99
            expected = torch.zeros(1, 53)
            expected[0, 0], expected[0, 52] = 2, 3
            torch.testing.assert_close(network(values), expected, rtol=0, atol=0)

    def test_synthetic_fit_has_only_central_targets_and_state_roundtrip(self):
        import torch
        raw = np.random.default_rng(5).normal(size=(16, 125, 62)).astype(np.float32)
        truth = raw[:, 36:89, 0] > .5
        params = dict(halo.HALO_MODEL_PARAMS, epochs=3)
        features = raw.reshape(16, -1)
        with patch.object(runner, 'remote_only'), redirect_stdout(io.StringIO()):
            model, fit = runner.fit_model(features, truth, params)
            self.assertEqual(fit['parameter_count'], 14465)
            self.assertEqual(fit['normalization_rows'], 16*53)
            self.assertEqual(fit['input_note_count'], 125)
            self.assertEqual(fit['output_note_count'], 53)
            np.testing.assert_array_equal(model.mean, context.fit_normalization(halo.central_features(features))[0])
            model.cutoff = .6
            probability = model.activity(features)
            self.assertEqual(probability.shape, (16, 53))
            self.assertEqual(model.activity(features[:0]).shape, (0, 53))
            with self.assertRaises(ValueError):
                model.activity(features[:, :-62])
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'model.pt'
                runner.save_model(path, model, halo.HarmonicHaloFeatures(), params)
                saved = torch.load(path, map_location='cpu', weights_only=True)
                self.assertEqual(saved['halo_parameters'], halo.HALO_PARAMETERS)
                self.assertEqual(saved['input_note_count'], 125)
                network = context.make_network(valid_context=saved['model_parameters']['padding'] == 'valid')
                network.load_state_dict(saved['state_dict'])
                restored = context.HarmonicContextModel(saved['mean'].numpy(), saved['scale'].numpy(),
                    network, saved['cutoff'], input_note_count=saved['input_note_count'])
                np.testing.assert_array_equal(restored.activity(features), probability)


if __name__ == '__main__':
    unittest.main()
