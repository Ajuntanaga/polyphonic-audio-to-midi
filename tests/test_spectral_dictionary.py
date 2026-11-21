"""Synthetic checks only; no recorded audio or model fitting on the laptop."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.optimize import nnls

from tools.direct_spectrum_learning import SETTINGS, trailing_context
from tools.spectral_dictionary import (PARAMETERS, DenseMagnitude, DictionaryModel,
    build_templates, fit_training_cutoff, stratified_summary, template_plan)


class SpectralDictionaryTests(unittest.TestCase):
    def test_qr_reduction_equals_direct_augmented_nnls(self):
        rng = np.random.default_rng(19)
        templates = rng.uniform(.01, 1, (31, 7))
        model = DictionaryModel(templates, [48, 48, 52, 56, 60, 64, 68])
        x = rng.uniform(0, 1, (4, 31))
        augmented = np.vstack([model.design, np.sqrt(PARAMETERS['ridge'])*np.eye(7)])
        expected = np.array([nnls(augmented, np.r_[row*model.weights, np.zeros(7)])[0] for row in x])
        np.testing.assert_allclose(model.coefficients(x), expected, rtol=1e-9, atol=1e-10)
        coefficients = model.coefficients(x)
        activity = model.activity(x)
        grouped = np.zeros((4, 53))
        for k, note in enumerate(model.notes):
            grouped[:, note-32] += coefficients[:, k]
        np.testing.assert_allclose(activity, grouped/grouped.max(axis=1, keepdims=True))
        np.testing.assert_array_equal(model.activity(np.zeros((1,31))), np.zeros((1,53)))

    def test_cutoff_includes_ties_and_uses_stricter_recall_tie(self):
        chosen = fit_training_cutoff(np.array([[.9, .8, .5]]), np.array([[1, 1, 0]]))
        self.assertTrue(chosen['feasible'])
        self.assertEqual(chosen['cutoff'], .8)
        self.assertEqual(chosen['true_positive'], 2)
        rejected = fit_training_cutoff(np.array([[.9, .9]]), np.array([[1, 0]]))
        self.assertFalse(rejected['feasible'])
        self.assertGreater(rejected['cutoff'], 1)
        zeros = fit_training_cutoff(np.zeros((1,2)), np.array([[1, 0]]))
        self.assertFalse(zeros['feasible'])
        values = np.r_[np.ones(100), .8, .7][None, :]
        truth = np.r_[np.ones(100), 0, 0][None, :]
        self.assertEqual(fit_training_cutoff(values, truth)['cutoff'], 1)

    def test_template_crops_train_only_and_inside_bounds(self):
        takes = [dict(role=role, key=role, stem=role, midi_note=60, string_mask=1,
                      start_sample=100, end_sample=20100) for role in ('train','calibration','test')]
        plan = template_plan(takes)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['source_key'], 'train')
        self.assertEqual(len(plan[0]['crops']), 9)
        self.assertEqual(plan[0]['crops'][0][0], 100)
        self.assertEqual(plan[0]['crops'][-1][1], 20100)
        for left, right in plan[0]['crops']:
            self.assertEqual(right-left, 16384)
            self.assertTrue(100 <= left < right <= 20100)
        with self.assertRaisesRegex(ValueError, 'Duplicate cell'):
            template_plan(takes+[takes[0]])

    def test_dense_features_are_past_only_and_linear_in_amplitude(self):
        extractor = DenseMagnitude()
        wave = np.sin(np.arange(20000)*2*np.pi*220/96000)
        a = extractor(trailing_context(wave, 19000))
        wave[19000:] = 1e9
        np.testing.assert_array_equal(a, extractor(trailing_context(wave, 19000)))
        np.testing.assert_allclose(extractor(2*trailing_context(wave, 19000)), 2*a)
        self.assertEqual(len(a), len(extractor.names))
        self.assertTrue((a >= 0).all())
        np.testing.assert_array_equal(extractor(np.zeros(16384)), np.zeros(len(a)))

    def test_empty_templates_fail_and_strata_reconcile(self):
        plan = [dict(stem='s', crops=[(0,16384)])]
        with self.assertRaisesRegex(ValueError, 'Silent training template'):
            build_templates(plan, {'s':np.zeros(16384)}, DenseMagnitude())
        truth = np.zeros((3,53), dtype=bool)
        truth[0,[48-32,60-32]] = True
        truth[1,[48-32,55-32]] = True
        result = stratified_summary(truth.astype(float), truth, .5)
        overall = result['summary']['overall']
        self.assertEqual(overall['exact_set_percent'], 100)
        strata = result['harmonic_relation_strata']
        self.assertEqual(strata['related']['overall']['examples'], 1)
        for key in ('examples','true_positive','false_positive','false_negative'):
            self.assertEqual(sum(s['overall'][key] for s in strata.values()), overall[key])

    def test_remote_guard_precedes_source_or_output_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_spectral_dictionary',
                '--spec', 'absent', '--output', str(output)], capture_output=True, text=True,
                env={k:v for k,v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
