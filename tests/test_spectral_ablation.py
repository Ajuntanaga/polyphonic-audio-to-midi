"""Synthetic mechanism checks; no recorded waveform/model access."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.optimize import nnls

from tools.direct_spectrum_learning import trailing_context, classification_summary
from tools.spectral_ablation import PARAMETERS, AveragedPower, CrossfitAblation, complete_chord_gate


class SpectralAblationTests(unittest.TestCase):
    def test_reduced_system_matches_direct_fit_and_refit(self):
        rng = np.random.default_rng(28)
        templates = rng.uniform(.01, 1, (24, 5))
        model = CrossfitAblation(templates, [48, 48, 52, 60, 67], np.arange(24)%2)
        y = rng.uniform(0, 1, 24)*model.weights
        for fold in (0,1):
            design = model.design[model.folds == fold]
            for removed in (None,48,52,60,67):
                keep = model.systems[fold][removed][0]
                augmented = np.vstack([design[:,keep], np.sqrt(PARAMETERS['ridge'])*np.eye(len(keep))])
                expected = nnls(augmented,np.r_[y[model.folds == fold],np.zeros(len(keep))])[0]
                actual = model._solve(fold,design.T@y[model.folds == fold],removed)
                np.testing.assert_allclose(actual[keep],expected,rtol=1e-8,atol=1e-10)
                if removed is not None:
                    self.assertTrue((actual[model.notes == removed] == 0).all())

    def test_quiet_pitch_has_support_without_being_strongest(self):
        templates = np.repeat(np.eye(4),2,axis=0)
        model = CrossfitAblation(templates,[48,60,64,67],np.arange(8)%2)
        x = (templates@np.array([1,.01,0,0]))[None,:]
        scores = model.activity(x)
        self.assertGreater(scores[0,60-32],.9)
        self.assertGreater(scores[0,48-32],.99)
        np.testing.assert_allclose(scores,model.activity(x*3),rtol=1e-10,atol=1e-10)
        self.assertEqual(np.count_nonzero(scores),2)
        np.testing.assert_array_equal(model.activity(np.zeros_like(x)),np.zeros((1,53)))

    def test_one_fold_only_feature_is_not_supported(self):
        templates = np.repeat(np.eye(2),2,axis=0)
        model = CrossfitAblation(templates,[48,60],np.arange(4)%2)
        scores = model.activity(np.array([[1,1,.5,0]]))
        self.assertEqual(scores[0,60-32],0)
        self.assertGreater(scores[0,48-32],0)

    def test_all_same_pitch_atoms_removed_as_group(self):
        templates = np.repeat(np.array([[1,1,0],[0,0,1]],float),2,axis=0)
        model = CrossfitAblation(templates,[48,48,60],np.arange(4)%2)
        self.assertEqual(model.systems[0][48][0].tolist(),[2])
        self.assertGreater(model.activity(np.array([[1,1,.1,.1]]))[0,48-32],.99)
        single = CrossfitAblation(np.ones((2,1)),[60],[0,1])
        self.assertGreater(single.activity(np.ones((1,2)))[0,60-32],.99)

    def test_power_quadratic_past_only_and_fold_coverage(self):
        extractor = AveragedPower()
        signal = np.sin(np.arange(20000)*2*np.pi*220/96000)
        context = trailing_context(signal,19000)
        features = extractor(context)
        np.testing.assert_allclose(extractor(2*context),4*features)
        signal[19000:] = 1e6
        np.testing.assert_array_equal(features,extractor(trailing_context(signal,19000)))
        self.assertEqual(len(features),len(extractor.names))
        self.assertEqual(set(extractor.folds.tolist()),{0,1})
        self.assertEqual(len(extractor.starts[4096]),7)
        self.assertEqual(len(extractor.starts[8192]),3)
        np.testing.assert_array_equal(extractor(np.zeros(16384)),np.zeros(len(features)))

    def test_each_complete_chord_gate_required(self):
        truth = np.zeros((5,53),bool)
        for row,n in enumerate([0,1,3,4,5]):
            truth[row,:n] = True
        self.assertTrue(complete_chord_gate(classification_summary(truth.astype(float),truth)))
        guess = truth.astype(float)
        guess[4,4] = 0
        self.assertFalse(complete_chord_gate(classification_summary(guess,truth)))
        self.assertFalse(complete_chord_gate(classification_summary(truth[:2].astype(float),truth[:2])))
        with self.assertRaisesRegex(ValueError,'Invalid power'):
            CrossfitAblation(np.ones((2,1)),[60],[0,1]).activity(np.array([[np.nan,1]]))

    def test_remote_guard_precedes_output_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'absent'
            result = subprocess.run([sys.executable,'-m','tools.portable_spectral_ablation',
                '--spec','absent','--output',str(output)],capture_output=True,text=True,
                env={k:v for k,v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode,0)
            self.assertIn('requires GitHub Actions',result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
