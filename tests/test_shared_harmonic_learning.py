"""Synthetic harmonic coordinates, shared output alignment and gate checks."""
import importlib.util
import unittest
from unittest.mock import patch

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, trailing_context
from tools.shared_harmonic_learning import (FEATURE_COUNT, NOTE_COUNT, HarmonicFeatures,
    SharedHarmonicModel, candidate_rows, summarize, acceptance_gate)
from tools.spectral_dictionary import IdentityTransform


class BinaryProbe:
    classes_ = np.array([False, True])
    def predict_proba(self, values):
        positive = values[:, 0]
        return np.c_[1-positive, positive]


class SharedHarmonicTests(unittest.TestCase):
    def test_harmonic_alignment_and_shared_coordinate_order(self):
        extractor = HarmonicFeatures()
        self.assertEqual((NOTE_COUNT, FEATURE_COUNT), (53, 62))
        self.assertEqual(len(extractor.coordinate_names), FEATURE_COUNT)
        self.assertEqual(len(extractor.names), NOTE_COUNT*FEATURE_COUNT)
        # A4 fundamental equals A3 harmonic2, and A4 subharmonic equals A3 fundamental.
        self.assertEqual(extractor.frequency[69-32, 1, 2], 440.0)
        self.assertEqual(extractor.frequency[57-32, 2, 2], 440.0)
        self.assertEqual(extractor.frequency[69-32, 0, 2], extractor.frequency[57-32, 1, 2])
        t = np.arange(16384)/96000
        values = extractor(.1*np.sin(2*np.pi*440*t)).reshape(NOTE_COUNT, FEATURE_COUNT)
        for window_start in (0, 31):
            self.assertEqual(values[69-32, window_start+7], values[57-32, window_start+12])
            self.assertEqual(values[69-32, window_start+2], values[57-32, window_start+7])
            self.assertGreater(values[69-32, window_start+7], values[72-32, window_start+7])
        self.assertEqual(values.dtype, np.float32)

    def test_relative_power_and_absolute_level_are_separate(self):
        extractor = HarmonicFeatures()
        rng = np.random.default_rng(31)
        context = rng.normal(0, .05, 16384)
        a = extractor(context).reshape(NOTE_COUNT, FEATURE_COUNT)
        b = extractor(2*context).reshape(NOTE_COUNT, FEATURE_COUNT)
        mask = np.ones(FEATURE_COUNT, bool)
        mask[[30, 61]] = False
        np.testing.assert_array_equal(a[:, mask], b[:, mask])
        np.testing.assert_allclose(b[:, ~mask]-a[:, ~mask], 20*np.log10(2), atol=3e-6)

    def test_trailing_context_is_causal_and_silence_finite(self):
        extractor = HarmonicFeatures()
        wave = np.arange(20000, dtype=float)/20000
        initial = extractor(trailing_context(wave, 10000))
        wave[10000:] = np.nan
        np.testing.assert_array_equal(initial, extractor(trailing_context(wave, 10000)))
        silence = extractor(np.zeros(16384)).reshape(NOTE_COUNT, FEATURE_COUNT)
        self.assertTrue(np.isfinite(silence).all())
        self.assertEqual(silence[0, 30], -120)
        for bad in (np.zeros(16383), np.full(16384, np.nan)):
            with self.assertRaises(ValueError):
                extractor(bad)

    def test_pooled_mapping_pitch_permutation_and_cutoff(self):
        values = np.zeros((2, NOTE_COUNT, FEATURE_COUNT), np.float32)
        expected = np.arange(2*NOTE_COUNT).reshape(2, NOTE_COUNT)/(2*NOTE_COUNT)
        values[:, :, 0] = expected
        flat = values.reshape(2, -1)
        np.testing.assert_array_equal(candidate_rows(flat)[:, 0], values[:, :, 0].ravel())
        model = SharedHarmonicModel(IdentityTransform(), BinaryProbe())
        np.testing.assert_allclose(model.activity(flat), expected, atol=1e-7)
        with self.assertRaisesRegex(ValueError, 'frozen'):
            model.predict_proba(flat)
        model.cutoff = .75
        np.testing.assert_array_equal(model.predict_proba(flat), values[:, :, 0] >= .75)
        shuffled = values[:, ::-1, :].reshape(2, -1)
        np.testing.assert_array_equal(model.activity(shuffled), model.activity(flat)[:, ::-1])
        model.cutoff = np.nextafter(1.0, 2.0)
        values[:, :, 0] = 1
        self.assertFalse(model.predict_proba(flat).any())

    def test_invalid_shapes_and_binary_classes_fail(self):
        for bad in (np.zeros(10), np.zeros((2, 10)), np.full((1, NOTE_COUNT*FEATURE_COUNT), np.inf)):
            with self.assertRaises(ValueError):
                candidate_rows(bad)
        probe = BinaryProbe()
        probe.classes_ = np.array([True])
        with self.assertRaisesRegex(ValueError, 'both binary'):
            SharedHarmonicModel(IdentityTransform(), probe).activity(np.zeros((1, NOTE_COUNT*FEATURE_COUNT)))
        values = np.zeros((1, NOTE_COUNT*FEATURE_COUNT))
        values[0, 0] = 2
        with self.assertRaisesRegex(ValueError, 'probabilities'):
            SharedHarmonicModel(IdentityTransform(), BinaryProbe()).activity(values)

    def test_training_and_all_chord_sizes_and_silence_are_gated(self):
        truth = np.zeros((4, NOTE_COUNT), bool)
        for row, size in enumerate((0, 3, 4, 5)):
            truth[row, :size] = True
        summary = summarize(truth.astype(float), truth, .5)['summary']
        self.assertTrue(acceptance_gate(summary, training=True))
        summary['overall']['precision_percent'] = 98
        self.assertTrue(acceptance_gate(summary))
        self.assertFalse(acceptance_gate(summary, training=True))
        summary['overall']['precision_percent'] = 100
        for count in ('3', '4', '5'):
            summary['by_distinct_pitch_count'][count]['exact_set_percent'] = 69
            self.assertFalse(acceptance_gate(summary))
            summary['by_distinct_pitch_count'][count]['exact_set_percent'] = 100
        summary['silence_false_predictions'] = 1
        self.assertFalse(acceptance_gate(summary))

    @unittest.skipUnless(importlib.util.find_spec('sklearn'), 'real sklearn API check runs on GitHub')
    def test_real_binary_fit_uses_pooled_training_scaler(self):
        from tools import portable_shared_harmonic_learning as runner
        rng = np.random.default_rng(23)
        values = rng.normal(size=(4, NOTE_COUNT*FEATURE_COUNT)).astype(np.float32)
        truth = values.reshape(4, NOTE_COUNT, FEATURE_COUNT)[:, :, 0] > 0
        with patch.object(runner, 'remote_only'), patch.dict(runner.MODEL_PARAMS, dict(verbose=False)):
            model, fit = runner.fit_model(values, truth)
        np.testing.assert_allclose(model.scaler.mean_, candidate_rows(values).mean(axis=0, dtype=float))
        self.assertEqual(model.activity(values).shape, truth.shape)
        self.assertEqual(fit['pooled_candidate_rows'], 4*NOTE_COUNT)
        self.assertFalse(fit['held_out_used'])


if __name__ == '__main__':
    unittest.main()
