import unittest
import numpy as np
from tools.refined_cross_pitch_shape import fit_refined_shape


class RefinedShapeTest(unittest.TestCase):
    def test_detuned_tone_and_validation_isolation(self):
        rate = 8000
        t = np.arange(1280) / rate
        y = np.cos(2*np.pi*165*2**(-22/1200)*t)
        a = fit_refined_shape(y, rate, [165], input_role='annotation_oracle')
        changed = y.copy()
        changed[640:] = np.sin(np.arange(640)) * 2
        b = fit_refined_shape(changed, rate, [165], input_role='annotation_oracle')
        self.assertEqual(a['refinement'], b['refinement'])
        self.assertAlmostEqual(a['refinement']['cents'][0], -22, places=3)
        self.assertLess(a['refined']['validation_residual_ratio'], 1e-8)
        self.assertGreater(b['refined']['validation_residual_ratio'], 1)

    def test_missing_pitch_not_added(self):
        t = np.arange(1280)/8000
        y = np.cos(2*np.pi*165*t) + .5*np.cos(2*np.pi*283*t)
        a = fit_refined_shape(y, 8000, [165], input_role='detector_candidates')
        self.assertEqual(len(a['refined']['fundamentals_hz']), 1)
        self.assertGreater(a['refined']['validation_residual_ratio'], .1)
        self.assertFalse(a['policy_admission'])

    def test_bound_and_silence(self):
        t = np.arange(1280)/8000
        a = fit_refined_shape(np.cos(2*np.pi*165*2**(55/1200)*t), 8000,
                              [165], input_role='annotation_oracle')
        self.assertTrue(a['refinement']['at_boundary'])
        self.assertLessEqual(abs(a['refinement']['cents'][0]), 35)
        b = fit_refined_shape(np.zeros(1280), 8000, [165], input_role='annotation_oracle')
        self.assertEqual(b['refinement_abstention'], 'silent_training')


class PairedAdditionTest(unittest.TestCase):
    def test_freezes_competitors_and_validation(self):
        from tools.refined_cross_pitch_shape import fit_paired_addition
        t = np.arange(1280)/8000
        y = np.cos(2*np.pi*163*t) + .4*np.cos(2*np.pi*283*t)
        a = fit_paired_addition(y, 8000, [165], 280, input_role='detector_candidates')
        changed = y.copy()
        changed[640:] = np.sin(np.arange(640))*2
        b = fit_paired_addition(changed, 8000, [165], 280, input_role='detector_candidates')
        self.assertEqual(a['with']['refinement'], b['with']['refinement'])
        self.assertEqual(a['without']['refined']['fundamentals_hz'][0],
                         a['with']['refined']['fundamentals_hz'][0])
        self.assertTrue(a['comparison_available'])
        self.assertGreater(a['validation_residual_reduction'], .1)
        self.assertFalse(a['policy_admission'])

    def test_silent_competitors_abstain(self):
        from tools.refined_cross_pitch_shape import fit_paired_addition
        a = fit_paired_addition(np.zeros(1280), 8000, [165], 280,
                                input_role='detector_candidates')
        self.assertEqual(a['abstention'], 'invalid_competing_fit')
