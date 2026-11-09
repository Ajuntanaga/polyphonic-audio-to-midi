import copy
import unittest

from tools.portable_partial_identity import feature, summarize


def frame(a, b, power=None):
    return dict(power=power or [1.0, 0.1, 0.1], partial_cents=[0, a, b])


def clips():
    return [dict(clip=f's{s}-p{p}.wav', string=s, **{'pass': p},
                 frames=[frame(2 + 8 * s, 3 + 8 * s) for _ in range(4)])
            for s in (3, 4) for p in (1, 2, 3)]


class PartialIdentityTests(unittest.TestCase):
    def test_heldout_attacks_cannot_change_training(self):
        data = clips()
        baseline = summarize(data, [3, 4])
        self.assertEqual(baseline['correctly_admitted_attacks'], 4)
        data[-1]['frames'] = [frame(26, 27) for _ in range(4)]
        changed = summarize(data, [3, 4])
        self.assertEqual(changed['prototypes'], baseline['prototypes'])
        self.assertEqual(changed['wrongly_admitted_attacks'], 1)
        self.assertFalse(changed['isolated_screen_pass'])

    def test_missing_training_partials_do_not_suppress_a_competitor(self):
        data = clips()
        data[0]['frames'] = [frame(0, 0, [1, 0, 0]) for _ in range(4)]
        result = summarize(data, [3, 4])
        self.assertFalse(result['all_feasible_prototypes_measured'])
        self.assertEqual(result['abstained_attacks'], 4)
        self.assertNotIn('3', result['prototypes'])

    def test_tied_profiles_and_large_distances_abstain(self):
        data = clips()
        for row in data:
            row['frames'] = [frame(1, 2) for _ in range(4)]
        self.assertEqual(summarize(data, [3, 4])['abstained_attacks'], 4)
        data = clips()
        data[1]['frames'] = [frame(-10, -10) for _ in range(4)]
        self.assertIsNone(summarize(data, [3, 4])['heldout'][0]['admitted_string'])

    def test_weak_or_search_edge_partials_are_unknown(self):
        self.assertFalse(feature([frame(0, 0, [1, 0.0001, 0.1])] * 4)['eligible'])
        self.assertFalse(feature([frame(39, 0)] * 4)['eligible'])
        self.assertTrue(feature([frame(0, 0)] * 4)['eligible'])

    def test_missing_string_or_holdout_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'coverage'):
            summarize(clips(), [2, 3, 4])
        data = [c for c in clips() if not (c['string'] == 3 and c['pass'] != 1)]
        with self.assertRaisesRegex(ValueError, 'holdouts'):
            summarize(data, [3, 4])
        data = [c for c in clips() if not (c['string'] == 3 and c['pass'] == 2)]
        with self.assertRaisesRegex(ValueError, 'holdouts'):
            summarize(data, [3, 4])
        data = clips()
        data.append(copy.deepcopy(data[0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            summarize(data, [3, 4])


if __name__ == '__main__':
    unittest.main()
