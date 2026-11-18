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

    def test_frozen_background_tracks_loss_without_refitting_nuisance(self):
        signal = .2 + np.cos(2*np.pi*300*np.arange(4800)/RATE)
        signal[3840:] = .2
        result = measure(self.prepared(signal), [300.])['frozen_background']
        self.assertTrue(result['available'])
        self.assertGreater(result['partials'][0]['training_coefficient_power'], 1)
        self.assertLess(result['partials'][0]['prediction_coefficient_power'], 1e-20)

    def test_frozen_background_retains_stationary_candidate(self):
        signal = .2 + np.cos(2*np.pi*300*np.arange(4800)/RATE + .3)
        result = measure(self.prepared(signal), [300.])['frozen_background']
        self.assertTrue(result['available'])
        partial = result['partials'][0]
        self.assertAlmostEqual(partial['training_coefficient_power'],
                               partial['prediction_coefficient_power'], places=8)

    def test_shared_gain_separates_background_change_from_candidate_loss(self):
        from tools.portable_ordinary_harmonic_prediction import design
        base = design([137.], 4800)
        background = .2 + 2*base[:, 1] + .4*base[:, 2]
        source = np.cos(2*np.pi*300*np.arange(4800)/RATE + .3)
        for retained in (True, False):
            signal = background + source
            signal[3840:] = 2.5*background[3840:] + (source[3840:] if retained else 0)
            prepared = dict(base=base, factor=admission.factor(base[:3840]), signal=signal)
            result = measure(prepared, [300.])['shared_background_gain']
            self.assertTrue(result['available'])
            self.assertAlmostEqual(result['background_gain'], 2.5, places=10)
            partial = result['partials'][0]
            if retained:
                self.assertAlmostEqual(partial['prediction_coefficient_power'],
                                       partial['training_coefficient_power'], places=8)
            else:
                self.assertLess(partial['prediction_coefficient_power'], 1e-20)

    def test_absent_background_does_not_invent_a_gain(self):
        signal = np.cos(2*np.pi*300*np.arange(4800)/RATE)
        result = measure(self.prepared(signal), [300.])['shared_background_gain']
        self.assertFalse(result['available'])
        self.assertEqual(result['reason'], 'no_resolvable_background_gain')

    def test_redundant_nuisance_is_distinguished_from_candidate_overlap(self):
        from tools.portable_ordinary_harmonic_prediction import design
        base = np.column_stack((np.ones(4800), np.ones(4800)))
        signal = design([300.], 4800)[:, 1]
        prepared = dict(base=base, factor=admission.factor(base[:3840]), signal=signal)
        result = measure(prepared, [300.])
        for segment in result['segments']:
            self.assertFalse(segment['available'])
            self.assertEqual(segment['nuisance_columns'], 2)
            self.assertEqual(segment['nuisance_rank'], 1)
            self.assertGreater(segment['conditional_singular_ratio'], .1)

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
