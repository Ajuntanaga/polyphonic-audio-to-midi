import csv
import io
import unittest

from tools.profile_pair_analysis import REQUIRED, analyze_stream, quantiles


def observation(**changes):
    row = dict.fromkeys(REQUIRED, 0)
    row.update(sample=64000, tick=1008, note=40, playable=7, final_primary=0,
        any_label=1, expected_note=1, expected_mask=1, voices='40:40:0,40:40:1',
        learned_cents='-5,5,0,0,0,0,0,0', group_proposal=3, group_origin=3,
        group_after=3, profile_fit_observed=1, profile_primary_error=.04,
        profile_best_single_error=.03, profile_mixture_error=.01,
        profile_weights='.6,.4,0,0,0,0,0,0', profile_observed='.5,.5,0,0,0,0',
        profile_single_errors='.04,.03,-1,-1,-1,-1,-1,-1')
    row.update(changes)
    return row


def analyze(*rows, **changes):
    stream = io.StringIO()
    columns = REQUIRED.union(*(set(row) for row in rows))
    writer = csv.DictWriter(stream, fieldnames=sorted(columns), delimiter='\t')
    writer.writeheader()
    writer.writerows(rows)
    stream.seek(0)
    capture = dict(rows=len(rows), truncated=False, decimation=16)
    capture.update(changes)
    return analyze_stream(stream, capture)


class ProfilePairAnalysisTests(unittest.TestCase):
    def test_correct_secondary_and_extra_secondary_are_counted_separately(self):
        result = analyze(observation(), observation(tick=1024, expected_mask=3),
            observation(tick=1040, expected_mask=0, expected_note=0),
            observation(tick=1056, expected_mask=0, expected_note=0, any_label=0))
        self.assertEqual(result['population'],
            dict(false_pair=1, true_pair=1, wrong_pitch=1, extra_gap=1))
        policy = next(p for p in result['policies'] if p['single_error_ceiling'] == .05
                      and p['mixture_ratio_floor'] == .25)
        for field in ('removed_correct', 'removed_wrong_string',
                      'removed_wrong_pitch', 'removed_extra_gap'):
            self.assertEqual(policy[field], 1)
        self.assertFalse(result['production_changed'])

    def test_unrendered_or_supported_pairs_do_not_become_projected_removals(self):
        result = analyze(observation(voices='40:40:0'),
            observation(tick=1024, group_after=1),
            observation(tick=1040, beat_valid=1),
            observation(tick=1056, fine_valid=1))
        self.assertEqual(result['totals']['independently_supported_pairs'], 2)
        self.assertEqual(result['totals'].get('rendered_secondary_eligible', 0), 0)
        self.assertTrue(all(p['removed_wrong_string'] == 0 for p in result['policies']))

    def test_bad_capture_and_invalid_normalization_are_rejected(self):
        with self.assertRaises(ValueError):
            analyze(observation(), rows=2)
        with self.assertRaises(ValueError):
            analyze(observation(), truncated=True)
        with self.assertRaises(ValueError):
            analyze(observation(profile_observed='.4,.4,0,0,0,0'))
        self.assertEqual(quantiles([1, 3])['p50'], 2)

    def test_phase_proximity_still_counts_a_real_secondary_as_harm(self):
        result = analyze(observation(phase_valid=1, phase_cents=-4.5),
            observation(tick=1024, phase_valid=1, phase_cents=-4.5, expected_mask=3),
            observation(tick=1040, phase_valid=0, phase_cents=-5))
        policy = next(p for p in result['phase_policies']
                      if p['primary_distance_ceiling'] == 1 and p['secondary_distance_floor'] == 8)
        self.assertEqual(policy['removed_wrong_string'], 1)
        self.assertEqual(policy['removed_correct'], 1)
        self.assertEqual(sum(policy['observations'].values()), 2)

    def test_recency_requires_recent_audio_and_keeps_correct_removals_visible(self):
        single = '1:2:0:0:0:0:1:0:0:0:0:0'
        pair = '1:2:.04:.03:.01:.4:.5:.5:0:0:0:0'
        stale = dict(profile_pair_primary=0, profile_pair_mask=3,
                     profile_pair_current=single, profile_pair_short=single,
                     profile_pair_long=pair, profile_uses_long_memory=1)
        result = analyze(observation(**stale),
            observation(tick=1024, expected_mask=3, **stale),
            observation(tick=1040, expected_mask=3, **dict(stale,
                        profile_pair_current=pair, profile_pair_short=pair)),
            observation(tick=1056, **dict(stale, profile_pair_current='0:0:0:0:0:0:0:0:0:0:0:0')))
        policy = next(p for p in result['recency_policies'] if p['window'] == 'current'
                      and p['gain_ratio_ceiling'] == .1 and p['blended_gain_floor'] == .01)
        self.assertEqual(policy['removed_wrong_string'], 1)
        self.assertEqual(policy['removed_correct'], 1)
        self.assertEqual(sum(policy['observations'].values()), 2)
        self.assertEqual(result['totals']['current_window_unavailable'], 1)
        self.assertTrue(result['recency_windows_available'])

    def test_recency_rejects_partial_schema_and_malformed_windows(self):
        with self.assertRaises(ValueError):
            analyze(observation(profile_pair_primary=0))
        fields = dict(profile_pair_primary=0, profile_pair_mask=3,
            profile_pair_current='1:1:0:0:0:0:.4:.4:0:0:0:0',
            profile_pair_short='0:0:0:0:0:0:0:0:0:0:0:0',
            profile_pair_long='0:0:0:0:0:0:0:0:0:0:0:0')
        with self.assertRaises(ValueError):
            analyze(observation(**fields))


if __name__ == '__main__':
    unittest.main()
