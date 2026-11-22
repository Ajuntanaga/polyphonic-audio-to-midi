"""Tiny generated signals only; model persistence is checked on GitHub."""
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tools.harmonic_pitch_scaled_windows import PITCH_SCALED_WINDOWS, HarmonicPitchScaledFeatures
from tools.shared_harmonic_learning import HarmonicFeatures, SETTINGS


class PitchScaledWindowTests(unittest.TestCase):
    def setUp(self):
        self.extractor = HarmonicPitchScaledFeatures()

    def test_layout_lengths_and_constant_cycle_count(self):
        extractor = self.extractor
        self.assertEqual(extractor.note_count, 53)
        self.assertEqual(len(extractor.coordinate_names), 62)
        self.assertEqual(len(set(extractor.names)), 53*62)
        self.assertEqual(extractor.names[0], 'note32:scaled_w4096:h0.5:offset-0.4:relative_db')
        self.assertEqual(extractor.names[-1], 'note84:scaled_w16384:rms_db')
        np.testing.assert_array_equal(extractor.window_lengths[0], [4096, 16384])
        np.testing.assert_array_equal(extractor.window_lengths[-1], [203, 813])
        self.assertTrue(np.all(np.diff(extractor.window_lengths, axis=0) < 0))
        # Rounding alone can move the cycle count by at most half a sample.
        frequency = 440*2**((np.arange(32, 85)-69)/12)
        cycles = extractor.window_lengths*frequency[:, None]/SETTINGS['sample_rate']
        expected = frequency[0]*np.array([4096, 16384])/SETTINGS['sample_rate']
        self.assertTrue(np.all(np.abs(cycles-expected) <= frequency[:, None]/(2*SETTINGS['sample_rate'])))

    def test_anchor_matches_original_features_exactly(self):
        time = np.arange(16384)/SETTINGS['sample_rate']
        rng = np.random.default_rng(20261122)
        for signal in (.1*np.sin(2*np.pi*51.913087*time), rng.normal(0, .05, 16384)):
            actual = self.extractor(signal).reshape(53, 62)
            original = HarmonicFeatures()(signal).reshape(53, 62)
            self.assertEqual(actual.dtype, np.float32)
            self.assertTrue(np.isfinite(actual).all())
            np.testing.assert_array_equal(actual[0], original[0])

    def test_each_candidate_ignores_samples_outside_its_trailing_context(self):
        signal = np.random.default_rng(23).normal(0, .05, 16384)
        original = self.extractor(signal).reshape(53, 62)
        for row in (12, 28, 52):
            short, long = self.extractor.window_lengths[row]
            older = signal.copy()
            older[:-long] += .3
            np.testing.assert_array_equal(self.extractor(older).reshape(53, 62)[row], original[row])
            between = signal.copy()
            between[-long:-short] += .3
            actual = self.extractor(between).reshape(53, 62)[row]
            np.testing.assert_array_equal(actual[:31], original[row, :31])
            self.assertFalse(np.array_equal(actual[31:], original[row, 31:]))

    def test_gain_normalization_and_silence(self):
        signal = np.random.default_rng(42).normal(0, .05, 16384)
        original = self.extractor(signal).reshape(53, 62)
        louder = self.extractor(2*signal).reshape(53, 62)
        relative = [index for index in range(62) if index not in (30, 61)]
        np.testing.assert_array_equal(louder[:, relative], original[:, relative])
        np.testing.assert_allclose(louder[:, [30, 61]]-original[:, [30, 61]],
                                   20*np.log10(2), atol=3e-6, rtol=0)
        silence = self.extractor(np.zeros(16384)).reshape(53, 62)
        np.testing.assert_array_equal(silence[:, relative], -80)
        np.testing.assert_array_equal(silence[:, [30, 61]], -120)

    def test_rejects_invalid_context(self):
        for value in (np.zeros(16383), np.zeros((1, 16384)), np.full(16384, np.nan), np.full(16384, np.inf)):
            with self.assertRaises(ValueError):
                self.extractor(value)


@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true', 'Model execution stays on GitHub')
class PitchScaledPersistenceTests(unittest.TestCase):
    def test_same_network_size_and_frozen_feature_metadata_roundtrip(self):
        import torch
        from tools import harmonic_context_learning as context
        from tools import portable_harmonic_context_learning as runner
        torch.set_num_threads(1)
        torch.manual_seed(context.SETWISE_PARAMS['seed'])
        network = context.make_network(62)
        self.assertEqual(sum(p.numel() for p in network.parameters()), 14465)
        model = context.HarmonicContextModel(np.zeros(62, np.float32), np.ones(62, np.float32), network, .6)
        features = np.random.default_rng(7).normal(size=(2, 53*62)).astype(np.float32)
        expected = model.activity(features)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'model.pt'
            extractor = HarmonicPitchScaledFeatures()
            runner.save_model(path, model, extractor, context.SETWISE_PARAMS)
            saved = torch.load(path, map_location='cpu', weights_only=True)
            self.assertEqual(saved['pitch_scaled_window_parameters'], PITCH_SCALED_WINDOWS)
            self.assertEqual(saved['window_lengths_by_candidate'], extractor.window_lengths.tolist())
            self.assertEqual(saved['feature_count'], 62)
            restored_network = context.make_network(saved['feature_count'])
            restored_network.load_state_dict(saved['state_dict'])
            restored = context.HarmonicContextModel(saved['mean'].numpy(), saved['scale'].numpy(),
                                                    restored_network, saved['cutoff'])
            np.testing.assert_array_equal(restored.activity(features), expected)


if __name__ == '__main__':
    unittest.main()
