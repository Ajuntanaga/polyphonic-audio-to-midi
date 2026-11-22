"""Pure synthetic checks; no recorded audio, model or inference is loaded."""
from copy import deepcopy
import unittest

import numpy as np

from tools.basic_pitch_adaptation import render_window
from tools.basic_pitch_release_adaptation import release_plan, render_release_window


def component(key, note=60):
    return dict(source_key=key, note=note, string_mask=1, crop_begin=0,
                length=43844, placement=0, gain_db=-6)


def row(i=0):
    return dict(example=i, role='train', gain_db=0,
                components=[component('a'), component('b', 64)])


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        # Deliberately different prefix/suffix levels expose accidental
        # re-normalization after shortening a component.
        self.clips = {'a': np.linspace(-.8, 1.3, 43844),
                      'b': np.linspace(.3, -.2, 43844)}

    def test_planner_preserves_inputs_and_is_deterministic(self):
        original = [row(i) for i in range(12)]
        saved = deepcopy(original)
        a = release_plan(original, count=7, seed=19)
        self.assertEqual(a, release_plan(original, count=7, seed=19))
        self.assertEqual(original, saved)
        self.assertEqual(len({r['parent_example'] for r in a}), 7)
        for r in a:
            self.assertEqual(r['components'], saved[r['parent_example']]['components'])
        with self.assertRaises(ValueError):
            release_plan(original, count=13)
        original[0]['role'] = 'test'
        with self.assertRaises(ValueError):
            release_plan(original, count=1)

    def test_original_view_is_exact(self):
        expected = render_window(row(), self.clips)
        actual = render_release_window(row(), self.clips)
        np.testing.assert_array_equal(actual[0], expected[0])
        np.testing.assert_array_equal(actual[1], expected[1])
        self.assertEqual(actual[2], expected[2])

    def test_release_preserves_prefix_gain_and_other_note(self):
        original = row()
        ended = dict(original, release=dict(component=0, end_sample=40960))
        before, truth, levels = render_window(original, self.clips)
        after, targets, end_levels = render_release_window(ended, self.clips)
        np.testing.assert_array_equal(after[:40850], before[:40850])
        self.assertEqual(end_levels[0]['normalization_gain'], levels[0]['normalization_gain'])
        self.assertEqual(end_levels[0]['crop_rms'], levels[0]['crop_rms'])
        other = dict(original, components=[original['components'][1]])
        other_signal, _, _ = render_window(other, self.clips)
        np.testing.assert_array_equal(after[40960:], other_signal[40960:])
        np.testing.assert_array_equal(targets[:, 64-21], truth[:, 64-21])
        self.assertTrue(targets[159, 60-21])
        self.assertFalse(targets[160:, 60-21].any())

    def test_same_pitch_survivor_keeps_occupancy(self):
        original = row()
        original['components'][1]['note'] = 60
        ended = dict(original, release=dict(component=0, end_sample=40960))
        _, truth, _ = render_window(original, self.clips)
        _, after, _ = render_release_window(ended, self.clips)
        np.testing.assert_array_equal(truth, after)

    def test_single_component_has_known_zero_suffix(self):
        original = row()
        original['components'] = original['components'][:1]
        ended = dict(original, release=dict(component=0, end_sample=40960))
        signal, truth, _ = render_release_window(ended, self.clips)
        self.assertFalse(signal[40960:].any())
        self.assertFalse(truth[160:].any())
        with self.assertRaises(ValueError):
            render_release_window(dict(original, release=dict(component=0, end_sample=100)), self.clips)


if __name__ == '__main__':
    unittest.main()
