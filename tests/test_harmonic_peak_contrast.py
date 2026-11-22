"""Synthetic signal measurements and feature-layout checks; no recordings."""
from contextlib import redirect_stdout
from importlib.util import find_spec
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import harmonic_peak_contrast as contrast
from tools import harmonic_context_learning as context
from tools import portable_harmonic_context_learning as runner


class PeakContrastTests(unittest.TestCase):
    def setUp(self):
        self.extractor = contrast.HarmonicContrastFeatures()
        self.time = np.arange(max(contrast.SETTINGS['windows']))/contrast.SETTINGS['sample_rate']

    def tone(self, note=69, cents=0, harmonics=1):
        frequency = 440*2**((note-69)/12+cents/1200)
        return sum(np.sin(2*np.pi*frequency*h*self.time)/h for h in range(1, harmonics+1))

    def row(self, audio, note=69, window=16384):
        values = self.extractor(audio).reshape(contrast.NOTE_COUNT, contrast.FEATURE_COUNT)
        wi = contrast.SETTINGS['windows'].index(window)
        start = contrast.BASE_FEATURE_COUNT+wi*contrast.PER_WINDOW
        return values[note-contrast.SETTINGS['note_low'], start:start+contrast.PER_WINDOW]

    def test_original_coordinates_are_bit_identical_and_layout_is_explicit(self):
        signal = self.tone(cents=25, harmonics=5)+.13*self.tone(note=57)
        result = self.extractor(signal).reshape(53, 106)
        original = self.extractor.base(signal).reshape(53, 62)
        np.testing.assert_array_equal(result[:, :62], original)
        self.assertEqual(len(self.extractor.coordinate_names), 106)
        self.assertEqual(len(set(self.extractor.names)), 53*106)
        self.assertTrue(np.isfinite(result).all())

    def test_detuned_peak_frequency_matches_signal_and_has_flank_contrast(self):
        for cents in (-25, 25):
            for window in contrast.SETTINGS['windows']:
                row = self.row(self.tone(cents=cents), window=window)
                self.assertEqual(row[3], 1)
                self.assertAlmostEqual(float(row[1]), cents, delta=.2)
                self.assertGreater(float(row[2]), 30)

    def test_consistent_partial_offsets_differ_from_one_detuned_partial(self):
        coherent = self.tone(cents=20, harmonics=5)
        base_frequency = 440*2**(20/1200)
        altered = coherent - np.sin(2*np.pi*base_frequency*2*self.time)/2
        altered += np.sin(2*np.pi*880*2**(-20/1200)*self.time)/2
        row = self.row(coherent)
        changed = self.row(altered)
        self.assertEqual(row[-1], 1)
        self.assertEqual(changed[-1], 1)
        self.assertLess(row[-2], .1)
        self.assertGreater(changed[-2], 10)

    def test_silence_is_explicit_and_outside_main_peak_is_not_reported(self):
        silence = self.row(np.zeros_like(self.time))
        self.assertTrue(np.isfinite(silence).all())
        np.testing.assert_array_equal(silence[:-2].reshape(5, 4)[:, 1:], np.zeros((5, 3)))
        np.testing.assert_array_equal(silence[-2:], [0, 0])
        shifted = self.row(self.tone(cents=70))
        # A weak sidelobe can be a valid local maximum; validity is not note presence.
        self.assertLess(abs(float(shifted[1])), contrast.CONTRAST['search_radius_cents'])
        self.assertLess(shifted[0], self.row(self.tone())[0]-20)

    def test_relative_features_preserve_global_gain_above_floors(self):
        signal = self.tone(cents=-18, harmonics=5)
        np.testing.assert_allclose(self.row(signal), self.row(signal*.1), atol=1e-4)

    def test_invalid_context_fails_before_fft(self):
        for bad in (self.time[:-1], np.full_like(self.time, np.nan)):
            with self.assertRaises(ValueError):
                self.extractor(bad)

    def test_descriptive_groups_keep_missing_and_false_cells_separate(self):
        features = np.array([self.extractor(self.tone()), self.extractor(np.zeros_like(self.time))])
        truth = np.zeros((2, 53), bool)
        truth[0, 69-32] = True
        truth[1, 60-32] = True
        probability = np.zeros((2, 53))
        probability[0, 69-32] = 1
        probability[0, 70-32] = 1
        result = contrast.contrast_summary(features, truth, probability, .5)
        for groups in result['windows'].values():
            self.assertEqual([groups[g]['candidate_cells'] for g in ('expected', 'found', 'missing', 'extra')],
                             [2, 1, 1, 1])
            self.assertEqual(groups['missing']['metrics']['mean_valid_prominence_db']['available'], 0)
        with self.assertRaises(ValueError):
            contrast.contrast_summary(features, truth[:1], probability, .5)

    def test_106_coordinate_scaler_keeps_pitch_and_coordinate_axes(self):
        features = np.zeros((2, 53, 106), np.float32)
        features[1, :, 105] = 2
        flat = features.reshape(2, -1)
        mean, scale = context.fit_normalization(flat, 106)
        normalized = context.normalized_context(flat, mean, scale, 106)
        self.assertEqual(normalized.shape, (2, 106, 53))
        np.testing.assert_array_equal(normalized[:, 105, :], np.tile([[-1], [1]], (1, 53)))
        with self.assertRaises(ValueError):
            context.fit_normalization(flat)


@unittest.skipUnless(find_spec('torch'), 'Pinned CPU torch fitting runs on GitHub only')
class PeakContrastNetworkTests(unittest.TestCase):
    def test_expanded_network_fit_and_persistence_roundtrip(self):
        import torch
        rng = np.random.default_rng(12)
        raw = rng.normal(size=(32, 53, 106)).astype(np.float32)
        truth = raw[:, :, -1] > .5
        features = raw.reshape(32, -1)
        params = dict(context.SETWISE_PARAMS, epochs=10)
        with patch.object(runner, 'remote_only'), redirect_stdout(io.StringIO()):
            model, fit = runner.fit_model(features, truth, params)
            self.assertEqual(fit['features_per_candidate'], 106)
            self.assertLess(fit['final_loss'], fit['loss_curve'][0])
            model.cutoff = .6
            probability = model.activity(features)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'model.pt'
                runner.save_model(path, model, contrast.HarmonicContrastFeatures(), params)
                saved = torch.load(path, map_location='cpu', weights_only=True)
                self.assertEqual(saved['feature_count'], 106)
                self.assertEqual(saved['contrast_parameters'], contrast.CONTRAST)
                network = context.make_network(saved['feature_count'])
                network.load_state_dict(saved['state_dict'])
                restored = context.HarmonicContextModel(saved['mean'].numpy(), saved['scale'].numpy(), network, .6)
                np.testing.assert_array_equal(restored.activity(features), probability)
                np.testing.assert_array_equal(restored.predict_proba(features), probability >= .6)


if __name__ == '__main__':
    unittest.main()
