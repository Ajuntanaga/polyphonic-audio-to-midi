"""Synthetic waveforms only: variation boundaries, useful response, role isolation."""
from copy import deepcopy
import importlib.util
import math
import unittest

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, render_mixture
from tools.harmonic_source_variation import (VARIATION, augment_training_plan,
                                              encoded_plan, shelf_component)


def plan():
    return [dict(example=i, role='train', gain_db=-6, components=[dict(
        source_key='take', stem='tone', string_mask=1, note=52, crop_begin=0,
        crop_end=16384, gain_db=-12)]) for i in range(100)]


class SourceVariationTests(unittest.TestCase):
    def test_repeatable_independent_parameters_leave_base_plan_intact(self):
        base = plan()
        original = deepcopy(base)
        varied = augment_training_plan(base)
        self.assertEqual(base, original)
        self.assertEqual(encoded_plan(varied), encoded_plan(augment_training_plan(base)))
        gains = [r['components'][0].pop('shelf_gain_db') for r in varied]
        self.assertEqual(varied, base)
        self.assertGreater(sum(g == 0 for g in gains), 0)
        self.assertGreater(sum(g != 0 for g in gains), 0)
        self.assertTrue(all(-6 <= g <= 6 for g in gains))
        other_labels = deepcopy(base)
        for row in other_labels:
            row['components'][0].update(note=70, string_mask=8, source_key='other')
        self.assertEqual(gains, [r['components'][0]['shelf_gain_db']
            for r in augment_training_plan(other_labels)])

    def test_held_out_and_repeat_augmentation_rejected(self):
        for role in ('calibration', 'test'):
            rows = plan()
            rows[-1]['role'] = role
            with self.assertRaisesRegex(ValueError, 'training role'):
                augment_training_plan(rows)
        with self.assertRaisesRegex(ValueError, 'already augmented'):
            augment_training_plan(augment_training_plan(plan()))

    def test_identity_transform_preserves_exact_audio_and_targets(self):
        clip = np.random.default_rng(1).normal(size=16384)
        base = plan()[0]
        varied = deepcopy(base)
        varied['components'][0]['shelf_gain_db'] = 0.0
        expected, labels = render_mixture(base, {'tone': clip})
        actual, targets = render_mixture(varied, {'tone': clip}, component_transform=shelf_component)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(targets, labels)
        self.assertIs(shelf_component(clip, dict(shelf_gain_db=0)), clip)

    def test_bounds_fail_closed(self):
        for gain in (-6.01, 6.01, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                shelf_component(np.ones(32), dict(shelf_gain_db=gain))

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'SciPy required; GitHub supplies pinned dependency')
    def test_shelf_changes_harmonic_balance_without_new_frequencies(self):
        n = 16384
        t = np.arange(n)
        clip = np.cos(2*np.pi*32*t/n) + 0.3*np.cos(2*np.pi*512*t/n)
        expected, labels = render_mixture(plan()[0], {'tone': clip})
        pole = math.exp(-2*math.pi*1000/SETTINGS['sample_rate'])
        for db in (-6., 6.):
            gain = 10**(db/20)
            row = deepcopy(plan()[0])
            row['components'][0]['shelf_gain_db'] = db
            actual, targets = render_mixture(row, {'tone': clip}, component_transform=shelf_component)
            np.testing.assert_array_equal(targets, labels)
            self.assertAlmostEqual(float(np.mean(expected**2)), float(np.mean(actual**2)), places=14)
            filtered = shelf_component(clip, dict(shelf_gain_db=db))
            bins = np.abs(np.fft.rfft(filtered[n//2:]))
            self.assertEqual(set(np.argsort(bins)[-2:]), {16, 256})
            measured_db = 20*np.log10((bins[256]/bins[16])/0.3)
            self.assertGreater(abs(measured_db), 3.0)
            self.assertEqual(np.sign(measured_db), np.sign(db))
            w = 2*np.pi*np.array([32, 512])/n
            response = gain+(1-gain)*(1-pole)/(1-pole*np.exp(-1j*w))
            self.assertAlmostEqual(measured_db, 20*np.log10(abs(response[1]/response[0])), places=9)
            full_w = np.linspace(0, np.pi, 1024)
            amplitude = abs(gain+(1-gain)*(1-pole)/(1-pole*np.exp(-1j*full_w)))
            self.assertGreaterEqual(float(amplitude.min()), min(1, gain)-1e-12)
            self.assertLessEqual(float(amplitude.max()), max(1, gain)+1e-12)
            np.testing.assert_allclose(shelf_component(np.ones(n), dict(shelf_gain_db=db)), 1, atol=1e-14)


if __name__ == '__main__':
    unittest.main()
