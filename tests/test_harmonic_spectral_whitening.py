"""Synthetic direct checks for one frame-local whitening representation."""
from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools.direct_spectrum_learning import trailing_context
from tools.shared_harmonic_learning import HarmonicFeatures, NOTE_COUNT, FEATURE_COUNT
from tools.harmonic_spectral_whitening import (CriticalBandWhitener,
    HarmonicWhitenedFeatures, WHITENING)


class SpectralWhiteningTests(unittest.TestCase):
    def test_band_geometry_and_hand_calculated_gain(self):
        whitener = CriticalBandWhitener(16384)
        anchors = 229*(10**((np.arange(32)+1)/21.4)-1)
        np.testing.assert_array_equal(whitener.centers, anchors[1:-1])
        # Direct scalar triangle construction checks the vectorized bank.
        for band in (0, 13, 29):
            for bin_index in (0, 10, 50, whitener.limit-1):
                freq = whitener.frequency[bin_index]
                expected = max(0, min((freq-anchors[band])/(anchors[band+1]-anchors[band]),
                    (anchors[band+2]-freq)/(anchors[band+2]-anchors[band+1])))
                self.assertAlmostEqual(whitener.weights[band, bin_index], expected)
        power = np.ones_like(whitener.frequency)
        variance = whitener.weights.sum(axis=1)/len(power)/16384
        gain = np.interp(whitener.frequency, anchors[1:-1],
                         np.maximum(variance, 1e-12/16384)**(-.67/2))
        expected = gain**2
        expected *= power.sum()/expected.sum()
        np.testing.assert_allclose(whitener(power), expected, rtol=1e-14)

    def test_silence_power_conservation_and_no_created_bins(self):
        for size in (4096, 16384):
            whitener = CriticalBandWhitener(size)
            zero = np.zeros(size//2+1)
            np.testing.assert_array_equal(whitener(zero), zero)
            power = zero.copy()
            power[[1, 17, 100, -1]] = [1e-20, 1, .02, 1e-8]
            result = whitener(power)
            self.assertTrue(np.isfinite(result).all())
            self.assertTrue(np.all(result >= 0))
            self.assertAlmostEqual(result.sum(), power.sum(), places=14)
            np.testing.assert_array_equal(result[power == 0], 0)
            np.testing.assert_allclose(whitener(power*.0001), result*.0001, rtol=1e-14)

    def test_smooth_spectral_tilt_is_reduced(self):
        whitener = CriticalBandWhitener(16384)
        power = (np.maximum(whitener.frequency, 100)/100)**-2
        flattened = whitener(power)
        selected = (whitener.frequency >= 200) & (whitener.frequency <= 5000)
        before = np.ptp(10*np.log10(power[selected]))
        after = np.ptp(10*np.log10(flattened[selected]))
        self.assertLess(after, before*.7)
        # A real change in spectral balance, not just global level normalization.
        self.assertGreater(after, 0)

    def test_layout_rms_and_gain_scaling(self):
        baseline, changed = HarmonicFeatures(), HarmonicWhitenedFeatures()
        wave = np.random.default_rng(9).normal(size=16384)
        spectral = np.ones(FEATURE_COUNT, bool)
        spectral[[30, 61]] = False
        for level in (0, 1e-8, .001, .1):
            a = baseline(wave*level).reshape(NOTE_COUNT, FEATURE_COUNT)
            b = changed(wave*level).reshape(NOTE_COUNT, FEATURE_COUNT)
            np.testing.assert_array_equal(b[:, [30, 61]], a[:, [30, 61]])
            self.assertEqual(b.dtype, np.float32)
            self.assertTrue(np.isfinite(b).all())
            if level == 0:
                np.testing.assert_array_equal(a, b)
        a = changed(.1*wave).reshape(NOTE_COUNT, FEATURE_COUNT)
        b = changed(.2*wave).reshape(NOTE_COUNT, FEATURE_COUNT)
        np.testing.assert_array_equal(a[:, spectral], b[:, spectral])
        self.assertEqual(len(changed.coordinate_names), 62)
        self.assertEqual(len(changed.names), NOTE_COUNT*62)
        self.assertEqual([changed.coordinate_names[i] for i in (30, 61)],
                         [baseline.coordinate_names[i] for i in (30, 61)])

    def test_trailing_causality_and_invalid_inputs(self):
        changed = HarmonicWhitenedFeatures()
        wave = np.random.default_rng(17).normal(size=20000)
        before = changed(trailing_context(wave, 10000))
        wave[10000:] = np.nan
        np.testing.assert_array_equal(changed(trailing_context(wave, 10000)), before)
        for invalid in (np.zeros(16383), np.full(16384, np.nan)):
            with self.assertRaises(ValueError):
                changed(invalid)
        whitener = CriticalBandWhitener(4096)
        for invalid in (np.zeros(2048), np.full(2049, np.nan), -np.ones(2049)):
            with self.assertRaises(ValueError):
                whitener(invalid)

    @unittest.skipUnless(find_spec('torch'), 'Pinned CPU torch check runs on GitHub only')
    def test_network_identity_and_serialized_whitening_metadata(self):
        import torch
        from tools import harmonic_context_learning as context
        from tools import portable_harmonic_context_learning as runner
        extractor = HarmonicWhitenedFeatures()
        torch.manual_seed(context.SETWISE_PARAMS['seed'])
        baseline = context.make_network(FEATURE_COUNT)
        torch.manual_seed(context.SETWISE_PARAMS['seed'])
        network = context.make_network(len(extractor.coordinate_names))
        self.assertEqual(sum(p.numel() for p in network.parameters()), 14465)
        for key, value in baseline.state_dict().items():
            self.assertTrue(torch.equal(value, network.state_dict()[key]))
        values = np.stack([extractor(np.zeros(16384)),
                           extractor(np.random.default_rng(8).normal(0, .1, 16384))])
        mean, scale = context.fit_normalization(values)
        model = context.HarmonicContextModel(mean, scale, network.eval(), .5)
        before = model.activity(values)
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'remote_only'):
            path = Path(directory)/'model.pt'
            runner.save_model(path, model, extractor, context.SETWISE_PARAMS)
            saved = torch.load(path, map_location='cpu', weights_only=True)
            self.assertEqual(saved['whitening_parameters'], WHITENING)
            self.assertEqual(saved['feature_count'], 62)
            self.assertEqual(saved['coordinate_names'], extractor.coordinate_names)
            restored = context.make_network(62)
            restored.load_state_dict(saved['state_dict'])
            model2 = context.HarmonicContextModel(saved['mean'].numpy(), saved['scale'].numpy(),
                                                  restored.eval(), saved['cutoff'])
            np.testing.assert_array_equal(model2.activity(values), before)


if __name__ == '__main__':
    unittest.main()
