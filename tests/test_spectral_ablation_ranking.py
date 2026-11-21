import unittest

import numpy as np

from tools.spectral_ablation_ranking import diagnose


def plan(notes):
    return [dict(example=i, role='train', components=[dict(note=n, gain_db=g,
        source_key=str(n)+'-'+str(j)) for j, (n, g) in enumerate(row)])
        for i, row in enumerate(notes)]


class RankingTest(unittest.TestCase):
    def test_strict_order_is_only_oracle_not_frozen_recovery(self):
        # Both genuine pitches beat the false pitch, but the fixed cutoff loses one.
        s, _ = diagnose([[.9, .4, .2]], np.array([[1, 1, 0]], bool),
                        plan([[(32, 0), (33, -12)]]), .8)
        self.assertEqual(s['nonsilent']['strict_separation_but_frozen_incomplete'], 1)
        self.assertEqual(s['frozen']['true_positive'], 1)
        self.assertEqual(s['frozen_missed_targets']['above_all_false'], 1)

    def test_false_above_weak_true_and_exact_tie_are_not_separable(self):
        s, _ = diagnose([[.9, .2, .5], [.8, .4, .4]],
            np.array([[1, 1, 0], [1, 1, 0]], bool),
            plan([[(32, 0), (33, -12)], [(32, 0), (33, -12)]]), .7)
        self.assertEqual(s['nonsilent']['strict_separation'], 0)
        self.assertEqual(s['nonsilent']['false_above_weakest'], 1)
        self.assertEqual(s['nonsilent']['exact_tie'], 1)

    def test_zero_ties_and_silence_remain_in_denominators(self):
        s, _ = diagnose(np.zeros((2, 3)), np.array([[1, 0, 0], [0, 0, 0]], bool),
                        plan([[(32, -24)], []]), .8)
        self.assertEqual(s['frozen']['complete_sets'], 1)
        self.assertEqual(s['frozen']['examples'], 2)
        self.assertEqual(s['nonsilent']['exact_tie'], 1)
        self.assertEqual(s['targets']['zero_activity'], 1)

    def test_unison_counts_one_pitch_and_keeps_level_disclosure(self):
        s, d = diagnose([[.9, .3, .1]], np.array([[1, 1, 0]], bool),
                        plan([[(32, -12), (32, -6), (33, 0)]]), .8)
        self.assertEqual(s['frozen']['expected'], 2)
        self.assertEqual(s['by_duplicate_pitch']['true']['mixtures']['examples'], 1)
        self.assertEqual(d['targets'][0]['relative_scheduled_gain_db'], -6)
        self.assertEqual(s['by_relative_scheduled_gain_db']['-6']['single_component_pitch']['expected'], 0)

    def test_wrong_target_or_role_fails(self):
        with self.assertRaises(ValueError):
            diagnose([[.9, .3]], np.array([[1, 0]], bool), plan([[(33, 0)]]), .8)
        p = plan([[(32, 0)]])
        p[0]['role'] = 'test'
        with self.assertRaises(ValueError):
            diagnose([[.9, .3]], np.array([[1, 0]], bool), p, .8)


if __name__ == '__main__':
    unittest.main()
