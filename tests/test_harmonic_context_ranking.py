import unittest

import numpy as np

from tools.harmonic_context_ranking import error_strata
from tools.spectral_ablation_ranking import diagnose


def analyse(activity, targets):
    truth = np.array(targets, dtype=bool)
    activity = np.array(activity, dtype=float)
    plan = [dict(example=i, role='train', components=[dict(note=int(j)+32,
        gain_db=0, source_key=str(j)) for j in np.flatnonzero(y)])
        for i, y in enumerate(truth)]
    _, details = diagnose(activity, truth, plan, .7)
    return error_strata(activity, truth, .7, details)


class ContextRankingTest(unittest.TestCase):
    def test_exclusive_errors_and_silence_account_for_every_example(self):
        s = analyse([[.9, .9, 0], [.9, .2, 0], [.9, .9, .8], [.9, .2, .8], [0, 0, 0]],
                    [[1, 1, 0]]*4+[[0, 0, 0]])
        self.assertEqual(s['by_distinct_pitch_count']['2'], dict(
            examples=4, exact=1, missing_only=1, extra_only=1, both=1,
            missing_pitches=2, extra_pitches=2))
        self.assertEqual(s['by_distinct_pitch_count']['0']['exact'], 1)

    def test_relations_have_exclusive_opportunity_denominators(self):
        truth = np.zeros((1, 53), bool)
        truth[0, [0, 24]] = True  # MIDI 32 and 56.
        activity = truth.astype(float)
        activity[0, 12] = .8  # MIDI 44 is both above 32 and below 56.
        s = analyse(activity, truth)
        r = s['harmonic_relation_strata']['all']
        self.assertEqual(r['both']['false_outputs'], 1)
        self.assertEqual(r['below_only']['expected'], 1)
        self.assertEqual(r['above_only']['expected'], 1)
        self.assertEqual(sum(v['expected'] for v in r.values()), 2)
        self.assertEqual(sum(v['false_opportunities'] for v in r.values()), 51)
        self.assertEqual(sum(v['false_outputs'] for v in r.values()), 1)

    def test_five_pitch_view_does_not_pool_other_polyphony(self):
        s = analyse([[.9, .9, .9, .9, .2, .1], [.9, .8, 0, 0, 0, 0]],
                    [[1, 1, 1, 1, 1, 0], [1, 0, 0, 0, 0, 0]])
        five = s['target_gain_strata']['five_pitch']['0']
        self.assertEqual(five['expected'], 5)
        self.assertEqual(five['missed'], 1)
        self.assertEqual(five['missed_above_all_false'], 1)
        r = s['harmonic_relation_strata']['five_pitch']
        self.assertEqual(sum(v['false_outputs'] for v in r.values()), 0)


if __name__ == '__main__':
    unittest.main()
