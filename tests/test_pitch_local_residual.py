"""Small numerical counterexamples only; no recorded audio or model access."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.optimize import nnls

from tools.pitch_local_residual import PitchLocalResidual, harmonic_masks
from tools.spectral_ablation import AveragedPower


def model_for(templates, notes, frequencies):
    return PitchLocalResidual(np.repeat(np.asarray(templates, float), 2, axis=0), notes,
        np.arange(2*len(frequencies)) % 2, np.repeat(frequencies, 2),
        np.ones(2*len(frequencies)))


class PitchLocalResidualTests(unittest.TestCase):
    def test_qr_projection_matches_unregularized_direct_nnls(self):
        rng = np.random.default_rng(28)
        templates = rng.uniform(.01, 1, (12, 4))
        # An identical atom makes the full system rank deficient.
        templates[:, 1] = templates[:, 0]
        model = model_for(templates, [48, 48, 60, 64], np.arange(12)*100+100)
        y = rng.uniform(0, 1, 24)*model.weights
        for fold in (0, 1):
            design = model.design[model.folds == fold]
            for removed in (None, 48, 60, 64):
                keep = model.systems[fold][removed][0]
                actual = model._nuisance(fold, y[model.folds == fold], removed)
                expected = nnls(design[:, keep], y[model.folds == fold])[0]
                # Nonunique coefficients are allowed; compare their projections.
                np.testing.assert_allclose(design@actual, design[:, keep]@expected,
                                           rtol=1e-8, atol=1e-10)

    def test_exact_parent_cannot_create_upper_from_shrinkage(self):
        f = 440*2**((48-69)/12)
        templates = np.array([[1, 0], [.4, 1], [.2, 0], [.1, .2]])
        model = model_for(templates, [48, 60], f*np.arange(1, 5))
        signal = np.repeat(templates[:, 0], 2)[None, :]
        for level in (.001, 1, 100):
            scores = model.activity(signal*level)
            self.assertEqual(scores[0, 60-32], 0)
            self.assertGreater(scores[0, 48-32], 0)

    def test_weak_pitch_and_silence_and_scale(self):
        notes = [48, 60, 64, 67]
        frequencies = 440*2**((np.asarray(notes)-69)/12)
        model = model_for(np.eye(4), notes, frequencies)
        signal = np.repeat([1, .001, 0, 0], 2)[None, :]
        scores = model.activity(signal)
        self.assertGreater(scores[0, 60-32], .99)
        self.assertGreater(scores[0, 48-32], .99)
        self.assertEqual(np.count_nonzero(scores), 2)
        np.testing.assert_allclose(scores, model.activity(signal*7), atol=1e-10)
        np.testing.assert_array_equal(model.activity(np.zeros_like(signal)), np.zeros((1, 53)))

    def test_inactive_global_group_still_receives_local_test(self):
        f = 440*2**((48-69)/12)
        model = model_for([[1, 0], [1, 1], [1, 2], [0, 1]], [48, 60], f*np.arange(1, 5))
        parent, upper = model.design[::2].T
        residual = np.array([0., .05, -1., .05])
        residual[0] = -(parent[1:]@residual[1:])/parent[0]
        self.assertLess(upper@residual, 0)
        weighted = np.repeat(100*parent+residual, 2)
        self.assertTrue((weighted >= 0).all())
        for fold in (0, 1):
            self.assertEqual(model._nuisance(fold, weighted[model.folds == fold])[1], 0)
        scores = model.activity((weighted/model.weights)[None, :])
        self.assertGreater(scores[0, 60-32], 0)
        self.assertGreater(model.diagnostics['positive_local_support_from_global_inactive'], 0)

    def test_one_fold_only_evidence_is_not_supported(self):
        model = model_for(np.eye(2), [48, 60], [130.8128, 261.6256])
        scores = model.activity(np.array([[1, 1, .5, 0]]))
        self.assertEqual(scores[0, 60-32], 0)
        self.assertGreater(scores[0, 48-32], 0)

    def test_same_pitch_duplicate_limit_and_empty_nuisance(self):
        one = model_for([[1], [.4]], [60], [261.6256, 523.2512])
        two = model_for([[1, 1], [.4, .4]], [60, 60], [261.6256, 523.2512])
        signal = np.array([[1, 1, .4, .4]])
        np.testing.assert_allclose(one.activity(signal), two.activity(signal), atol=1e-10)
        self.assertGreater(one.activity(signal)[0, 60-32], .99)

    def test_geometry_is_feature_aligned_and_overlap_weighted(self):
        extractor = AveragedPower()
        self.assertEqual(len(extractor.frequency_hz), len(extractor.names))
        self.assertEqual(len(extractor.bin_width_hz), len(extractor.names))
        for name, frequency, width in zip(extractor.names, extractor.frequency_hz, extractor.bin_width_hz):
            bin_index = int(name.split(':')[1][3:])
            self.assertAlmostEqual(frequency, bin_index*width)
        masks = harmonic_masks(extractor.frequency_hz, extractor.bin_width_hz)
        support = (masks > 0).sum(axis=0)
        np.testing.assert_allclose((masks*masks).sum(axis=0), support > 0, atol=1e-12)

    def test_bad_input_fails_and_remote_guard_precedes_io(self):
        model = model_for([[1]], [60], [261.6256])
        with self.assertRaisesRegex(ValueError, 'Invalid power'):
            model.activity(np.array([[np.nan, 1]]))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_pitch_local_residual',
                '--spec', 'absent', '--output', str(output)], capture_output=True, text=True,
                env={k:v for k,v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
