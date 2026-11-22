"""Synthetic controls for the single absolute-level-input suppression screen."""
from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools.direct_spectrum_learning import trailing_context
from tools.shared_harmonic_learning import HarmonicFeatures, FEATURE_COUNT, NOTE_COUNT
from tools.harmonic_context_learning import fit_normalization, normalized_context
from tools.harmonic_level_suppression import HarmonicLevelBlindFeatures, SUPPRESSION


class LevelSuppressionTests(unittest.TestCase):
    def test_only_absolute_slots_change_at_all_levels(self):
        original, changed = HarmonicFeatures(), HarmonicLevelBlindFeatures()
        rng = np.random.default_rng(42)
        noise = rng.normal(size=16384)
        keep = np.ones(FEATURE_COUNT, bool)
        keep[SUPPRESSION['coordinate_indices']] = False
        for level in (0, 1e-8, .001, .1):
            with self.subTest(level=level):
                before = original(noise*level).reshape(NOTE_COUNT, FEATURE_COUNT)
                after = changed(noise*level).reshape(NOTE_COUNT, FEATURE_COUNT)
                np.testing.assert_array_equal(after[:, keep], before[:, keep])
                np.testing.assert_array_equal(after[:, ~keep], 0)
                self.assertTrue(np.isfinite(after).all())
                self.assertEqual(after.dtype, np.float32)
        self.assertEqual(len(changed.coordinate_names), 62)
        self.assertEqual(len(changed.names), NOTE_COUNT*62)
        self.assertEqual([changed.coordinate_names[i] for i in (30, 61)],
                         ['w4096:rms_db:suppressed_zero', 'w16384:rms_db:suppressed_zero'])

    def test_gain_invariance_above_floors_and_floor_limit(self):
        extractor = HarmonicLevelBlindFeatures()
        noise = np.random.default_rng(6).normal(size=16384)
        np.testing.assert_array_equal(extractor(.05*noise), extractor(.1*noise))
        # The experiment must not be described as level-invariant near silence.
        self.assertFalse(np.array_equal(extractor(1e-7*noise), extractor(2e-7*noise)))

    def test_normalized_zero_slots_cannot_restore_level(self):
        extractor = HarmonicLevelBlindFeatures()
        noise = np.random.default_rng(7).normal(size=16384)
        values = np.stack([extractor(level*noise) for level in (0, .001, .1)])
        mean, scale = fit_normalization(values)
        np.testing.assert_array_equal(mean[[30, 61]], 0)
        np.testing.assert_array_equal(scale[[30, 61]], 1)
        np.testing.assert_array_equal(normalized_context(values, mean, scale)[:, [30, 61], :], 0)
        held_out = np.stack([extractor(.2*noise)])
        np.testing.assert_array_equal(normalized_context(held_out, mean, scale)[:, [30, 61], :], 0)

    def test_causality_and_invalid_context(self):
        extractor = HarmonicLevelBlindFeatures()
        wave = np.random.default_rng(8).normal(size=20000)
        before = extractor(trailing_context(wave, 10000))
        wave[10000:] = np.nan
        np.testing.assert_array_equal(before, extractor(trailing_context(wave, 10000)))
        for bad in (np.zeros(16383), np.full(16384, np.nan)):
            with self.assertRaises(ValueError):
                extractor(bad)

    @unittest.skipUnless(find_spec('torch'), 'Pinned CPU torch check runs on GitHub only')
    def test_same_network_initialization_and_saved_metadata(self):
        import torch
        from tools import harmonic_context_learning as context
        from tools import portable_harmonic_context_learning as runner
        original, suppressed = HarmonicFeatures(), HarmonicLevelBlindFeatures()
        torch.manual_seed(context.SETWISE_PARAMS['seed'])
        baseline = context.make_network(len(original.coordinate_names))
        torch.manual_seed(context.SETWISE_PARAMS['seed'])
        network = context.make_network(len(suppressed.coordinate_names))
        self.assertEqual(sum(p.numel() for p in network.parameters()), 14465)
        for key, value in baseline.state_dict().items():
            self.assertTrue(torch.equal(value, network.state_dict()[key]))
        values = np.stack([suppressed(np.zeros(16384)),
                           suppressed(np.random.default_rng(9).normal(0, .1, 16384))])
        mean, scale = fit_normalization(values)
        model = context.HarmonicContextModel(mean, scale, network.eval(), .5)
        before = model.activity(values)
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'remote_only'):
            path = Path(directory)/'model.pt'
            runner.save_model(path, model, suppressed, context.SETWISE_PARAMS)
            saved = torch.load(path, map_location='cpu', weights_only=True)
            self.assertEqual(saved['suppression_parameters'], SUPPRESSION)
            self.assertEqual(saved['feature_count'], 62)
            self.assertEqual(saved['coordinate_names'], suppressed.coordinate_names)
            restored = context.make_network(62)
            restored.load_state_dict(saved['state_dict'])
            model2 = context.HarmonicContextModel(saved['mean'].numpy(), saved['scale'].numpy(),
                                                 restored.eval(), saved['cutoff'])
            np.testing.assert_array_equal(model2.activity(values), before)


if __name__ == '__main__':
    unittest.main()
