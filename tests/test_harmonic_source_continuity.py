"""Synthetic numerical contracts; run with the offloaded harmonic tests."""
import unittest
import numpy as np

from tools import harmonic_admission_cues as admission
from tools.harmonic_source_continuity import measure
from tools.portable_ordinary_harmonic_prediction import RATE


class SourceContinuityTests(unittest.TestCase):
    def prepared(self, signal):
        base = np.ones((4800, 1))
        return dict(base=base, factor=admission.factor(base[:3840]), signal=signal)

    def test_stationary_partial_keeps_power_across_disjoint_segments(self):
        clock = np.arange(4800) / RATE
        signal = .2 + np.cos(2*np.pi*300*clock + .3)
        result = measure(self.prepared(signal), [300.])
        self.assertEqual(result['status'], 'measured')
        powers = [s['partials'][0]['coefficient_power'] for s in result['segments']]
        np.testing.assert_allclose(powers, powers[0], rtol=1e-10)

    def test_observed_source_loss_is_not_hidden_by_training_power(self):
        signal = np.cos(2*np.pi*300*np.arange(4800)/RATE)
        signal[3840:] = 0
        result = measure(self.prepared(signal), [300.])
        self.assertEqual(result['status'], 'measured')
        self.assertGreater(result['segments'][1]['partials'][0]['coefficient_power'], 1)
        self.assertEqual(result['segments'][2]['partials'][0]['coefficient_power'], 0)

    def test_future_samples_are_rejected_instead_of_used(self):
        with self.assertRaisesRegex(ValueError, 'exactly the observed'):
            measure(self.prepared(np.zeros(4801)), [300.])

    def test_no_separable_partials_is_unavailable(self):
        from tools.portable_ordinary_harmonic_prediction import design
        base = design([300.], 4800)
        prepared = dict(base=base, factor=admission.factor(base[:3840]), signal=base[:, 1])
        result = measure(prepared, [300.])
        self.assertEqual(result['reason'], 'no_independent_lower_partials')


if __name__ == '__main__':
    unittest.main()
