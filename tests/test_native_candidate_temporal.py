import unittest

import numpy as np

from tools.candidate_outcome_analysis import CANDIDATE_FIELDS_V4
from tools.native_candidate_temporal import (BASE_NAMES, FEATURE_NAMES, CausalHistory,
    addition_spans, base_features, eligible, full_interval_targets)
from tools.portable_native_candidate_temporal import parse_trace


def candidate(note=60, **changes):
    row = {name:0 for name in CANDIDATE_FIELDS_V4}
    row.update(note=note, energy_observed=1, score_ratio=0.5, direct=1, local=1,
               fund_ratio=0.4, score_energy=0.02, fund_energy=0.008)
    row.update(changes)
    return row


def trace(rows, annotation=''):
    lines = ['# m3_candidate_outcome_v5\n',
        'sample\ttick\tquiet\tsignal_samples\tlabels\tmatched_labels\tvoices\tcandidates\tinput_power\tfloor_stats\n']
    for i, candidates in enumerate(rows):
        tuples = ','.join(':'.join(str(c[f]) for f in CANDIDATE_FIELDS_V4) for c in candidates)
        lines.append(f'{i*64+63}\t{i+1}\t0\t0\t{annotation}\tignored\tignored\t{tuples}\t.1\tignored\n')
    return lines


class NativeCandidateTemporalTest(unittest.TestCase):
    def test_sufficient_legacy_predicate_requires_direct_and_peak_or_evidence(self):
        self.assertTrue(eligible(candidate(), 0))
        self.assertTrue(eligible(candidate(local=0, evidence=1), 0))
        for changes in ({'direct':0}, {'local':0}, {'score_ratio':0.1999},
                        {'energy_observed':0}):
            self.assertFalse(eligible(candidate(**changes), 0))
        self.assertFalse(eligible(candidate(), 5))

    def test_invalid_measurements_are_missing(self):
        row = base_features(candidate(onset=99, phase_cents=99), .1)
        self.assertTrue(np.isnan(row[BASE_NAMES.index('onset')]))
        self.assertTrue(np.isnan(row[BASE_NAMES.index('phase_abs_cents')]))
        valid = base_features(candidate(onset=99, onset_observed=1,
                                        phase_cents=-12, phase_valid=1), .1)
        self.assertEqual(valid[BASE_NAMES.index('phase_abs_cents')], 12)

    def test_annotation_columns_and_forced_rows_cannot_affect_features(self):
        rows = [[candidate()], [candidate(score_ratio=.6)], [candidate()]]
        a = parse_trace(trace(rows), 192)
        # Even arbitrary annotation text is never parsed as a feature. A forced
        # row that fails legacy inclusion is discarded before history storage.
        extra = candidate(61, direct=0, score_ratio=100)
        b = parse_trace(trace([r+[extra] for r in rows], 'changed-label-answer'), 192)
        np.testing.assert_array_equal(a['features'], b['features'])
        np.testing.assert_array_equal(a['notes'], b['notes'])

    def test_excluded_history_is_not_observed_zero_or_forced_evidence(self):
        history = CausalHistory()
        history.frame(1, 0, {60:candidate(direct=0, score_ratio=999)}, .1)
        _, row = history.frame(2, 0, {60:candidate()}, .1)[0]
        self.assertTrue(np.isnan(row[FEATURE_NAMES.index('score_ratio_lag1')]))

    def test_only_past_same_pitch_lags_are_used(self):
        history = CausalHistory()
        history.frame(1, 0, {60:candidate(score_ratio=.7),61:candidate(61,score_ratio=90)}, .1)
        _, row = history.frame(2, 0, {60:candidate(score_ratio=.8)}, .1)[0]
        self.assertAlmostEqual(row[FEATURE_NAMES.index('score_ratio_lag1')], .7, places=6)
        saved = row.copy()
        history.frame(3, 0, {60:candidate(score_ratio=999)}, .1)
        np.testing.assert_array_equal(row, saved)

    def test_ring_expires_missing_ticks(self):
        history = CausalHistory()
        history.frame(1, 0, {60:candidate(score_ratio=.9)}, .1)
        for tick in range(2,66): history.frame(tick, 0, {}, .1)
        _, row = history.frame(66, 0, {60:candidate()}, .1)[0]
        self.assertTrue(np.isnan(row[FEATURE_NAMES.index('score_ratio_lag64')]))

    def test_clock_is_next_sample_and_no_eof_interval(self):
        data = parse_trace(trace([[candidate()]]*3), 192)
        np.testing.assert_array_equal(data['starts'], [64,128])
        np.testing.assert_array_equal(data['ends'], [128,192])

    def test_incomplete_or_discontinuous_trace_fails(self):
        with self.assertRaises(ValueError): parse_trace(trace([[candidate()]]), 128)
        malformed = trace([[candidate()]]*2)
        malformed[-1] = malformed[-1].replace('127\t2\t', '128\t2\t')
        with self.assertRaises(ValueError): parse_trace(malformed,128)

    def test_annotation_target_requires_complete_interval(self):
        labels=[dict(start_sample=64,end_sample=192,midi_note=60)]
        y=full_interval_targets(np.array([64,128,160,64]),np.array([128,192,224,128]),
            np.array([60,60,60,61]),labels,256)
        np.testing.assert_array_equal(y,[True,True,False,False])

    def test_output_never_backdates_or_extends_selected_intervals(self):
        spans=addition_spans(np.array([.9,.8,.99]),.85,np.array([64,128,192]),
            np.array([128,192,256]),np.array([60,60,61]),256)
        self.assertEqual(spans,[(64,128,60),(192,256,61)])

    def test_feature_order_has_no_identity_or_label_fields(self):
        self.assertEqual(len(set(FEATURE_NAMES)),len(FEATURE_NAMES))
        self.assertFalse(set(FEATURE_NAMES) & {'note','tick','sample','labels','matched_labels',
            'voices','pitch_band','best_string','assigned_mask','signal_samples'})


if __name__ == '__main__': unittest.main()
