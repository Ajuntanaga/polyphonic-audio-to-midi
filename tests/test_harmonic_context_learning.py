"""Synthetic context, train-only scaling, fitting and persistence checks."""
from contextlib import redirect_stdout
from importlib.util import find_spec
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import harmonic_context_learning as context
from tools import portable_harmonic_context_learning as runner


class ContextFeaturesTests(unittest.TestCase):
    def test_normalization_pools_only_supplied_training_rows(self):
        raw = np.zeros((3, context.NOTE_COUNT, context.FEATURE_COUNT), np.float32)
        raw[:, :, 0] = np.arange(3)[:, None]
        raw[:, :, 1] = np.arange(context.NOTE_COUNT)[None, :]
        raw[:, :, 2] = 5
        flat = raw.reshape(3, -1)
        mean, scale = context.fit_normalization(flat)
        np.testing.assert_allclose(mean[:3], [1, 26, 5])
        normalized = context.normalized_context(flat, mean, scale)
        self.assertEqual(normalized.shape, (3, context.FEATURE_COUNT, context.NOTE_COUNT))
        np.testing.assert_allclose(normalized.mean(axis=(0, 2)), 0, atol=1e-7)
        self.assertEqual(scale[2], 1)
        held_out = flat.copy()+100
        before = mean.copy(), scale.copy()
        shifted = context.normalized_context(held_out, mean, scale)
        self.assertGreater(shifted.mean(), 50)
        np.testing.assert_array_equal(mean, before[0])
        np.testing.assert_array_equal(scale, before[1])
        # Preserve pitch and coordinate axes, not an accidental flattened convolution.
        self.assertAlmostEqual(float(normalized[0, 1, 52]), (52-26)/scale[1], places=6)

    def test_feature_extraction_is_unchanged(self):
        from tools.shared_harmonic_learning import HarmonicFeatures
        self.assertIs(context.HarmonicFeatures, HarmonicFeatures)
        self.assertEqual(context.FEATURE_COUNT, 62)
        self.assertEqual(context.NOTE_COUNT, 53)

    def test_invalid_shapes_and_scalers_fail(self):
        values = np.zeros((2, context.NOTE_COUNT*context.FEATURE_COUNT))
        with self.assertRaises(ValueError):
            context.fit_normalization(values[:0])
        for mean, scale in (([0], [1]), (np.zeros(62), np.zeros(62)),
                            (np.full(62, np.nan), np.ones(62))):
            with self.assertRaises(ValueError):
                context.normalized_context(values, mean, scale)
        with self.assertRaises(ValueError):
            context.normalized_context(values[:, :-1], np.zeros(62), np.ones(62))

    def test_cutoff_is_required_before_prediction(self):
        model = context.HarmonicContextModel(None, None, None)
        with self.assertRaises(ValueError):
            model.predict_proba(np.zeros((1, 53*62)))


@unittest.skipUnless(find_spec('torch'), 'Pinned CPU torch fit runs on GitHub only')
class ContextNetworkTests(unittest.TestCase):
    def test_remote_dependency_present_when_on_github(self):
        import torch
        self.assertFalse(torch.cuda.is_available())

    def test_output_receives_neighboring_pitch_context(self):
        import torch
        torch.set_num_threads(1)
        network = context.make_network()
        # A transparent synthetic path: own coordinate -> one 12-semitone link -> readout.
        with torch.no_grad():
            for parameter in network.parameters():
                parameter.zero_()
            network.input.weight[0, 0, 0] = 1
            network.context[2].weight[0, 0, 2] = 1
            network.output.weight[0, 0, 0] = 1
        values = torch.zeros(2, context.FEATURE_COUNT, context.NOTE_COUNT, requires_grad=True)
        with torch.no_grad():
            values[0, 0, 30] = 1
        result = network(values)
        self.assertEqual(tuple(result.shape), (2, 53))
        self.assertEqual(float(result[0, 18]), 1)
        self.assertEqual(float(result[1, 18]), 0)
        self.assertEqual(float(values[0, 0, 18]), 0)
        result[0, 18].backward()
        self.assertGreater(float(values.grad[0, 0, 30]), 0)

    def test_synthetic_fit_frozen_cutoff_and_state_roundtrip(self):
        import torch
        rng = np.random.default_rng(5)
        raw = rng.normal(size=(32, 53, 62)).astype(np.float32)
        truth = raw[:, :, 0] > 0.5
        features = raw.reshape(32, -1)
        with patch.object(runner, 'remote_only'), patch.dict(context.MODEL_PARAMS, epochs=10), redirect_stdout(io.StringIO()):
            model, fit = runner.fit_model(features, truth)
            self.assertEqual(fit['fits'], 1)
            self.assertFalse(fit['held_out_used'])
            self.assertEqual(fit['epochs'], 10)
            self.assertLess(fit['final_loss'], fit['loss_curve'][0])
            probability = model.activity(features)
            self.assertEqual(probability.shape, truth.shape)
            self.assertTrue(np.isfinite(probability).all())
            model.cutoff = .6
            np.testing.assert_array_equal(model.predict_proba(features), probability >= .6)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'model.pt'
                runner.save_model(path, model, context.HarmonicFeatures())
                saved = torch.load(path, map_location='cpu', weights_only=True)
                restored_network = context.make_network()
                restored_network.load_state_dict(saved['state_dict'])
                restored = context.HarmonicContextModel(saved['mean'].numpy(), saved['scale'].numpy(),
                    restored_network, saved['cutoff'])
                np.testing.assert_array_equal(restored.activity(features), probability)


if __name__ == '__main__':
    unittest.main()
