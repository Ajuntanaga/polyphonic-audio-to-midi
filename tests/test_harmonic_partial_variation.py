"""Synthetic checks: phase-preserving bounded variation and unchanged targets."""
from copy import deepcopy
import unittest

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, render_mixture
from tools.harmonic_partial_variation import (augment_training_plan, frequency_gain,
                                              partial_component)
from tools.harmonic_source_variation import encoded_plan


def plan():
    return [dict(example=i, role='train', gain_db=-6, components=[dict(
        source_key='take', stem='tone', string_mask=1, note=52, crop_begin=0,
        crop_end=16384, gain_db=-12)]) for i in range(100)]


class PartialVariationTests(unittest.TestCase):
    def test_seeded_independent_gains_preserve_plan_and_ignore_source_identity(self):
        base = plan()
        original = deepcopy(base)
        varied = augment_training_plan(base)
        self.assertEqual(base, original)
        self.assertEqual(encoded_plan(varied), encoded_plan(augment_training_plan(base)))
        gains = [r['components'][0].pop('partial_gain_db') for r in varied]
        self.assertEqual(varied, base)
        a = np.array(gains)
        identity = np.all(a == 0, axis=1)
        self.assertGreater(identity.sum(), 0)
        self.assertGreater((~identity).sum(), 0)
        self.assertTrue(np.all((-6 <= a) & (a <= 6)))
        self.assertTrue(np.all(np.ptp(a[~identity], axis=1) > 0))
        other = deepcopy(base)
        for row in other:
            row['components'][0].update(note=70, string_mask=8, source_key='other')
        self.assertEqual(gains, [r['components'][0]['partial_gain_db']
                                for r in augment_training_plan(other)])

    def test_held_out_and_double_augmentation_rejected(self):
        for role in ('calibration', 'test'):
            rows = plan()
            rows[-1]['role'] = role
            with self.assertRaisesRegex(ValueError, 'training role'):
                augment_training_plan(rows)
        with self.assertRaisesRegex(ValueError, 'already augmented'):
            augment_training_plan(augment_training_plan(plan()))

    def test_identity_preserves_exact_audio_and_targets(self):
        clip = np.random.default_rng(1).normal(size=16384)
        base = plan()[0]
        row = deepcopy(base)
        row['components'][0]['partial_gain_db'] = [0]*5
        expected, target = render_mixture(base, {'tone': clip})
        actual, labels = render_mixture(row, {'tone': clip}, component_transform=partial_component)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(labels, target)
        self.assertIs(partial_component(clip, row['components'][0]), clip)

    def test_independent_anchors_unity_edges_and_bounded_smooth_interpolation(self):
        f0 = 440*2**((52-69)/12)
        gains = np.array([6, -6, 3, -2, 1.])
        np.testing.assert_allclose(frequency_gain(f0*np.arange(1, 6), 52, gains),
                                   10**(gains/20), atol=1e-14)
        np.testing.assert_array_equal(frequency_gain(np.array([0, .25*f0, .5*f0, 6*f0, 48000]),
                                                    52, gains), np.ones(5))
        response = frequency_gain(np.linspace(0, 48000, 10000), 52, gains)
        self.assertGreaterEqual(response.min(), 10**(-6/20)-1e-14)
        self.assertLessEqual(response.max(), 10**(6/20)+1e-14)

    def test_no_new_fft_bins_or_phase_change_and_component_power_is_restored(self):
        n = 16384
        t = np.arange(n)
        bins = np.array([28, 56, 84, 112, 140])
        phase = np.array([.1, -.4, .7, -.9, .3])
        clip = np.cos(2*np.pi*t[:, None]*bins/n+phase).sum(axis=1)
        row = deepcopy(plan()[0])
        component = row['components'][0]
        component['partial_gain_db'] = [6, -6, 3, -2, 1]
        changed = partial_component(clip, component)
        before, after = np.fft.rfft(clip), np.fft.rfft(changed)
        expected = frequency_gain(bins*SETTINGS['sample_rate']/n, 52, component['partial_gain_db'])
        np.testing.assert_allclose(after[bins]/before[bins], expected, atol=1e-13)
        residue = after.copy()
        residue[bins] = 0
        self.assertLess(float(np.abs(residue).max()), 1e-8)
        clean, targets = render_mixture(plan()[0], {'tone': clip})
        actual, labels = render_mixture(row, {'tone': clip}, component_transform=partial_component)
        self.assertAlmostEqual(float(np.mean(clean**2)), float(np.mean(actual**2)), places=14)
        np.testing.assert_array_equal(labels, targets)
        np.testing.assert_array_equal(partial_component(np.zeros(n), component), np.zeros(n))

    def test_invalid_bounds_shapes_and_pitch_rejected(self):
        for gains in ([0]*4, [0]*6, [0, 0, 0, 0, 6.01], [-6.01]*5,
                      [float('nan')]*5, [float('inf')]*5):
            with self.assertRaises(ValueError):
                frequency_gain([100], 52, gains)
        for note in (31, 85, True, 52.1):
            with self.assertRaises(ValueError):
                frequency_gain([100], note, [0]*5)
        for values in (np.zeros(16), np.full(16384, np.nan)):
            with self.assertRaises(ValueError):
                partial_component(values, dict(note=52, partial_gain_db=[0]*5))
        for frequency in ([-1], [48001], [float('nan')]):
            with self.assertRaises(ValueError):
                frequency_gain(frequency, 52, [0]*5)


if __name__ == '__main__':
    unittest.main()
