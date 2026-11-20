import unittest
import numpy as np
from tools.cross_pitch_shape_fit import fit_shape


class CrossPitchContracts(unittest.TestCase):
    rate = 8000

    def signal(self, frequencies, amplitudes):
        t = np.arange(1280)/self.rate
        return sum(a*np.cos(2*np.pi*f*t+.3*i) for i,(f,a) in enumerate(zip(frequencies,amplitudes)))

    def test_overlapping_mainlobes_recovered_at_known_frequencies(self):
        y = self.signal([165,330,185,370], [1,.4,.7,.2])
        r = fit_shape(y,self.rate,[165,185],input_role='annotation_oracle',harmonics=2)
        self.assertTrue(r['shape_available'])
        np.testing.assert_allclose(r['harmonic_power'],[[1,.16],[.49,.04]],atol=1e-10)
        self.assertLess(r['validation_residual_ratio'],1e-20)

    def test_shared_harmonics_abstain(self):
        y = self.signal([165,330,660],[1,.4,.2])
        r = fit_shape(y,self.rate,[165,330],input_role='annotation_oracle',harmonics=2)
        self.assertFalse(r['shape_available'])
        self.assertEqual(r['abstention'],'unidentifiable_coefficients')

    def test_omitted_competitor_leaves_residual(self):
        y = self.signal([165,330,185,370],[1,.4,.7,.2])
        r = fit_shape(y,self.rate,[165],input_role='detector_candidates',harmonics=2)
        self.assertGreater(r['validation_residual_ratio'],.1)
        self.assertFalse(r['policy_admission'])

    def test_validation_never_changes_fitted_shape(self):
        y = self.signal([165,330],[1,.4])
        before = fit_shape(y,self.rate,[165],input_role='annotation_oracle',harmonics=2)
        y[640:] += self.signal([401],[2])[640:]
        after = fit_shape(y,self.rate,[165],input_role='annotation_oracle',harmonics=2)
        self.assertEqual(before['harmonic_power'],after['harmonic_power'])
        self.assertGreater(after['validation_residual_ratio'],1)

    def test_silence_and_role(self):
        r = fit_shape(np.zeros(1280),self.rate,[165],input_role='detector_candidates')
        self.assertEqual(r['abstention'],'silent_training')
        with self.assertRaises(ValueError):
            fit_shape(np.zeros(1280),self.rate,[165],input_role='unknown')

if __name__ == '__main__':
    unittest.main()
