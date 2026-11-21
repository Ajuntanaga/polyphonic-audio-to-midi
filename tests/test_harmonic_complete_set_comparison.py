import unittest

import numpy as np

from tools.harmonic_complete_set_comparison import paired_changes, require_pair


def compare(b, c, y, bc=.7, cc=.4, plan=None):
    truth = np.asarray(y, dtype=bool)
    if plan is None:
        plan = [dict(example=i, role='train', components=[dict(note=int(j)+32,
            gain_db=0, source_key=str(j)) for j in np.flatnonzero(row)])
            for i, row in enumerate(truth)]
    return paired_changes(np.asarray(b), np.asarray(c), truth, bc, cc, plan)


class CompleteSetComparisonTest(unittest.TestCase):
    def test_uses_both_frozen_cutoffs_and_keeps_gains_separate_from_losses(self):
        s, changed = compare([[.8, .1, 0], [.2, .1, 0], [.8, .8, 0], [0, 0, 0]],
            [[.5, .5, 0], [.5, .1, 0], [.5, .1, 0], [0, 0, 0]],
            [[1, 0, 0]]*3+[[0, 0, 0]])
        self.assertEqual(s['overall'], dict(examples=4, baseline_exact=2,
            current_exact=3, exact_gained=2, exact_lost=1, exact_both=1,
            exact_neither=0, genuine_gained=1, genuine_lost=0,
            false_new=1, false_removed=1, false_persistent=0))
        self.assertEqual(len(changed), 3)
        self.assertEqual(s['single_pitch_exact_losses'][0]['example'], 0)
        self.assertEqual(s['single_pitch_exact_losses'][0]['current']['extra'], [33])
        self.assertNotIn('0', s['ordering_by_distinct_pitch_count'])

    def test_ordering_improvement_is_distinct_from_frozen_cutoff_success(self):
        s, _ = compare([[.6, .65]], [[.3, .2]], [[1, 0]])
        self.assertEqual(s['overall']['current_exact'], 0)
        o = s['ordering_by_distinct_pitch_count']['1']
        self.assertEqual(o['separation_gained'], 1)
        self.assertEqual(o['current_separated_but_incomplete'], 1)
        self.assertEqual(o['baseline_ordering_failure'], 1)

    def test_duplicate_pitch_gain_uses_loudest_component_once(self):
        plan = [dict(example=0, role='train', components=[
            dict(note=32, gain_db=-24, source_key='a'),
            dict(note=32, gain_db=-18, source_key='b'),
            dict(note=33, gain_db=0, source_key='c')])]
        s, _ = compare([[.1, .9, 0]], [[.5, .2, 0]], [[1, 1, 0]], plan=plan)
        rows = s['target_gain_transitions']['all']
        self.assertEqual(rows['-18.0'], dict(expected=1, baseline_missing=1,
            current_missing=0, gained=1, lost=0))
        self.assertEqual(rows['0.0']['lost'], 1)
        self.assertEqual(sum(x['expected'] for x in rows.values()), 2)

    def test_harmonic_relations_are_exclusive_with_full_false_denominator(self):
        y = np.zeros((1, 53), bool); y[0, [0, 24]] = True
        b = y.astype(float); c = b.copy(); c[0, 12] = .5
        s, _ = compare(b, c, y)
        rows = s['false_harmonic_transitions']['all']
        self.assertEqual(rows['both']['new'], 1)
        self.assertEqual(sum(r['opportunities'] for r in rows.values()), 51)
        self.assertEqual(sum(r['new'] for r in rows.values()), 1)
        self.assertEqual(sum(r['new'] for r in
            s['false_harmonic_transitions']['single_pitch'].values()), 0)

    def test_silence_false_outputs_are_not_discarded(self):
        s, changed = compare([[0, 0]], [[.5, 0]], [[0, 0]])
        self.assertEqual(s['by_distinct_pitch_count']['0']['exact_lost'], 1)
        self.assertEqual(s['overall']['false_new'], 1)
        self.assertIsNone(changed[0]['current']['strict_separation'])
        self.assertEqual(s['target_gain_transitions']['all'], {})

    def test_pair_identity_rejects_changed_target_or_crop(self):
        a = np.array([[True, False]])
        require_pair(a, a.copy(), [{'crop': 1}], [{'crop': 1}])
        with self.assertRaisesRegex(ValueError, 'targets'):
            require_pair(a, ~a, [], [])
        with self.assertRaisesRegex(ValueError, 'plans'):
            require_pair(a, a, [{'crop': 1}], [{'crop': 2}])


if __name__ == '__main__':
    unittest.main()
