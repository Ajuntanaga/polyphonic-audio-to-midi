import copy
import unittest

import numpy as np

from tools.saved_source_transfer import diagnose


def source(key, note, string, role='test'):
    return dict(source_key=key, stem=key, midi_note=note, string_mask=string,
                role=role, calibration_pass=3, consistency_status='unexamined',
                start_sample=0, end_sample=20000)


def component(s, begin=0, gain=0):
    return dict(source_key=s['source_key'], stem=s['stem'], note=s['midi_note'],
                string_mask=s['string_mask'], crop_begin=begin, crop_end=begin+16384, gain_db=gain)


def analyze(sources, components, detected, gains=None):
    plan = [dict(example=i, role='test', gain_db=(gains[i] if gains else 0), components=cs)
            for i, cs in enumerate(components)]
    truth = np.zeros((len(plan), 53), bool)
    probability = np.zeros_like(truth, dtype=float)
    for i, (cs, ps) in enumerate(zip(components, detected)):
        for c in cs:
            truth[i, c['note']-32] = True
        for note in ps:
            probability[i, note-32] = .8
    return diagnose(probability, truth, plan, .5, {s['source_key']: s for s in sources}, 'test')


class SavedSourceTransferTest(unittest.TestCase):
    def test_unison_is_not_singleton_and_missing_coverage_stays_unknown(self):
        a, b = source('a', 60, 1), source('b', 60, 2)
        s, rows = analyze([a, b], [[component(a)], [component(a), component(b)]], [[60], []])
        self.assertEqual(s['singleton']['examples'], 1)
        self.assertEqual(s['mixed_one_distinct_pitch']['false_negative'], 1)
        self.assertEqual(s['mixed_unison_targets'], dict(expected=1, missing=1))
        self.assertEqual(rows[0]['singleton_status'], 'always_exact_observed')
        self.assertEqual(rows[1]['singleton_status'], 'unknown')
        self.assertEqual(sum(len(r['mixed_unique_pitch_by_cardinality']) for r in rows), 0)

    def test_false_only_singleton_is_error_and_mixed_example_counted_once(self):
        a, b = source('a', 60, 1), source('b', 64, 2)
        s, rows = analyze([a, b], [[component(a)], [component(b)],
                                [component(a), component(b)]], [[60, 72], [64], [72]])
        self.assertEqual(rows[0]['singleton_target_miss_n'], 0)
        self.assertEqual(rows[0]['singleton_status'], 'never_exact')
        self.assertEqual(rows[0]['singleton_false_notes'], {'72': 1})
        g = s['mixed_example_groups']['some_singleton_error']
        self.assertEqual((g['examples'], g['false_negative'], g['false_positive']), (1, 2, 1))
        self.assertEqual(sum(r['mixed_exact_fail_exposure_n'] for r in rows), 2)

    def test_matching_requires_same_crop_and_effective_scheduled_level(self):
        a, b = source('a', 60, 1), source('b', 64, 2)
        s, _ = analyze([a, b], [[component(a, gain=-6)], [component(b)],
            [component(a), component(b)], [component(a, begin=1), component(b)],
            [component(a), component(b)]], [[60], [64], [64], [64], [64]], [0, 0, -6, -6, 0])
        p = s['scheduled_crop_level_matches']
        self.assertEqual(p['mixed_unique_pitch_targets'], 6)
        self.assertEqual(p['targets_with_match'], 2)  # a at row2; b at row4
        self.assertEqual(p['mixed_missing_despite_all_matched_singletons_found'], 1)

    def test_silence_extras_and_mixed_source_buckets_reconcile(self):
        a, b, c = source('a', 60, 1), source('b', 64, 2), source('c', 67, 4)
        s, _ = analyze([a, b, c], [[component(a)], [component(b)], [component(b)],
            [component(a), component(b)], [component(a), component(c)], []],
            [[60], [64], [], [60], [60, 67], [72]])
        self.assertEqual(s['sources_by_singleton_status']['sometimes_exact']['sources'], 1)
        self.assertEqual(s['sources_by_singleton_status']['unknown']['sources'], 1)
        self.assertEqual(s['mixed_example_groups']['otherwise_unknown']['complete_sets'], 1)
        self.assertEqual(s['silence']['false_positive'], 1)
        self.assertEqual(s['frozen']['false_negative'], 2)

    def test_role_metadata_and_targets_fail_closed(self):
        a = source('a', 60, 1)
        plan = [dict(example=0, role='test', gain_db=0, components=[component(a)])]
        truth = np.zeros((1, 53), bool); truth[0, 28] = True
        def call(p, y, sources):
            return diagnose(truth.astype(float), y, p, .5, sources, 'test')
        with self.assertRaisesRegex(ValueError, 'targets'):
            call(plan, np.zeros_like(truth), {'a': a})
        changed = copy.deepcopy(plan); changed[0]['components'][0]['crop_end'] += 1
        with self.assertRaisesRegex(ValueError, 'identity'):
            call(changed, truth, {'a': a})
        with self.assertRaisesRegex(ValueError, 'role'):
            call(plan, truth, {'a': dict(a, role='train')})


if __name__ == '__main__':
    unittest.main()
