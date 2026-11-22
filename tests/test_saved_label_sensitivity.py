import unittest

import numpy as np

from tools.saved_label_sensitivity import analyze


def fixture(components, predicted):
    truth = np.zeros((len(components), 53), bool)
    probability = np.zeros_like(truth, dtype=float)
    plan = []
    for i, (cs, notes) in enumerate(zip(components, predicted)):
        for key, note in cs:
            truth[i, note-32] = True
        for note in notes:
            probability[i, note-32] = .8
        plan.append(dict(example=i, components=[dict(source_key=k, note=n) for k, n in cs]))
    return probability, truth, plan


class SavedLabelSensitivityTest(unittest.TestCase):
    def test_shared_original_pitch_survives_replacement(self):
        p, y, plan = fixture([[('a', 60), ('b', 60)]], [[60, 64]])
        s, rows = analyze(p, y, plan, .5, {'a': 64}, {'a'})
        self.assertEqual(rows[0]['hypothetical_notes'], [60, 64])
        self.assertEqual(s['overall']['hypothetical']['complete_sets'], 1)
        self.assertEqual(s['overall']['cardinality_changed'], 1)
        self.assertIn('1', s['by_original_distinct_pitch_count'])

    def test_new_unison_merges_without_dropping_example(self):
        p, y, plan = fixture([[('a', 60), ('b', 64)]], [[64]])
        s, rows = analyze(p, y, plan, .5, {'a': 64}, {'a'})
        self.assertEqual(rows[0]['hypothetical_notes'], [64])
        self.assertEqual(s['overall']['hypothetical']['expected'], 1)
        self.assertEqual(s['by_original_distinct_pitch_count']['2']['hypothetical']['examples'], 1)

    def test_bound_grants_affected_rows_once_and_preserves_other_errors(self):
        p, y, plan = fixture([[('a', 60), ('b', 64)], [('c', 67)], [('d', 69)], []],
                            [[], [], [69], []])
        s, rows = analyze(p, y, plan, .5, {'a': 64, 'b': 68}, {'a', 'b', 'c'})
        self.assertEqual(len(rows), 1)
        bound = s['overall']['optimistic_bounds']
        self.assertEqual(bound['eight_non_octave']['complete_set_upper_bound'], 3)
        self.assertEqual(bound['all_fifteen']['complete_set_upper_bound'], 4)
        self.assertEqual(s['overall']['hypothetical']['complete_sets'], 2)

    def test_already_exact_affected_example_can_lose_without_bound_double_count(self):
        p, y, plan = fixture([[('a', 60)], [('b', 64)]], [[60], [64]])
        s, _ = analyze(p, y, plan, .5, {'a': 64}, {'a'})
        self.assertEqual(s['overall']['lost_exact'], 1)
        self.assertEqual(s['overall']['optimistic_bounds']['eight_non_octave']['complete_set_upper_bound'], 2)

    def test_invalid_original_target_or_replacement_rejected(self):
        p, y, plan = fixture([[('a', 60)]], [[60]])
        with self.assertRaisesRegex(ValueError, 'out of range'):
            analyze(p, y, plan, .5, {'a': 100}, {'a'})
        with self.assertRaisesRegex(ValueError, 'targets differ'):
            analyze(p, ~y, plan, .5, {'a': 64}, {'a'})


if __name__ == '__main__':
    unittest.main()
