import io
import unittest

from tools.candidate_outcome_analysis import (
    CANDIDATE_FIELDS, CANDIDATE_FIELDS_V1, HEADER, analyze_candidate_population, analyze_label_failures,
    analyze_group_failures, analyze_fret_relief, analyze_calibrated_harmonic_admission, compare_streams,
)


def candidate(note=40, **features):
    row = dict.fromkeys(CANDIDATE_FIELDS, 0)
    row.update(note=note, score_ratio=.4, fund_ratio=.6, direct=1,
               best_cal=.95, second_cal=.91, best_string=0, playable_mask=3)
    row.update(features)
    return ':'.join(str(row[name]) for name in CANDIDATE_FIELDS)


def frame(sample, labels='', matched='', voices='', candidates='', quiet=0):
    return f'{sample}\t{sample // 100}\t{quiet}\t{sample}\t{labels}\t{matched}\t{voices}\t{candidates}\n'


def stream(*rows):
    return io.StringIO('# m3_candidate_outcome_v2\n' + HEADER + ''.join(rows))


class CandidateOutcomeAnalysisTests(unittest.TestCase):
    def test_added_removed_outputs_and_group_recovery_have_separate_counts(self):
        a = stream(
            frame(100, '0:40:3', '', '40:40:0:0:10:1:0:3', candidate()),
            frame(200, '0:40:3', '', '40:40:3:2:1:1:0:0', candidate()),
            frame(300, '', '', '52:52:2:3:1:1:0:0', candidate(52)))
        b = stream(
            frame(100, '0:40:3', '0', '40:40:0:0:10:1:0:3,40:40:1:0:10:1:0:3', candidate()),
            frame(200, '0:40:3', '', '41:41:3:1:1:1:0:0', candidate(41)),
            frame(300))
        expected_a = dict(labeled=2, matched=0, false_positive_voices=2,
                          false_wrong_note_voices=0, false_wrong_string_voices=1, false_gap_voices=1)
        expected_b = dict(labeled=2, matched=1, false_positive_voices=1,
                          false_wrong_note_voices=1, false_wrong_string_voices=0, false_gap_voices=0)
        result = compare_streams(a, b, expected_a, expected_b)
        self.assertEqual(result['changes']['matched_labels_gained'], 1)
        self.assertEqual(result['changes']['added/correct_voice'], 1)
        self.assertEqual(result['changes']['removed/wrong_string'], 1)
        self.assertEqual(result['changes']['removed/extra_gap_output'], 1)
        self.assertEqual(result['changes']['added/wrong_note'], 1)
        self.assertEqual(result['control']['correct_voice'], 1)
        self.assertEqual(result['trial']['correct_voice'], 2)
        self.assertEqual(result['label_changes'], {'gained/note40/mask3': 1})
        self.assertEqual(result['feature_outcomes']['added/trial/score_ratio/<0.6'],
                         {'correct_voice': 1, 'wrong_note': 1})

    def test_identical_outputs_do_not_create_feature_changes(self):
        row = frame(100, '0:40:1', '0', '40:40:0:0:10:1:0:0', candidate())
        result = compare_streams(stream(row), stream(row))
        self.assertEqual(result['control'], result['trial'])
        self.assertEqual(result['feature_outcomes'], {})
        self.assertEqual(result['examples'], [])

    def test_pair_alignment_length_and_metric_mismatches_fail(self):
        row = frame(100, '0:40:1')
        for a, b in [(stream(row), stream()), (stream(), stream(row)),
                     (stream(row), stream(frame(101, '0:40:1'))),
                     (stream(row), stream(frame(100, '0:41:1'))),
                     (stream(row, row), stream(row, row))]:
            with self.subTest(), self.assertRaises(ValueError):
                compare_streams(a, b)
        wrong = dict(labeled=1, matched=1, false_positive_voices=0,
                     false_wrong_note_voices=0, false_wrong_string_voices=0, false_gap_voices=0)
        with self.assertRaisesRegex(ValueError, 'trace/report mismatch for matched'):
            compare_streams(stream(row), stream(row), wrong)

    def test_invalid_labels_outcomes_and_nonfinite_features_fail(self):
        for bad in [frame(100, '', '0'), frame(100, voices='40:40:0:4:1:0:0:0'),
                    frame(100, voices='40:40:0:1:1:0:0:0', candidates=candidate(score_ratio='nan'))]:
            with self.subTest(), self.assertRaises(ValueError):
                compare_streams(stream(frame(100)), stream(bad))

    def test_fundamental_share_cannot_exceed_total_harmonic_energy(self):
        for share in (-.01, 1.2):
            with self.subTest(share=share), self.assertRaisesRegex(ValueError, 'fundamental share'):
                analyze_candidate_population(stream(frame(100, candidates=candidate(
                    local=1, fund_ratio=share))))


class CalibratedHarmonicAdmissionTests(unittest.TestCase):
    def pair(self, active=0, upper_changes=None):
        upper = dict(selection=4, cal_direct=1, score_ratio=.4, fund_ratio=.98,
                     playable_mask=192, active=active)
        upper.update(upper_changes or {})
        return ','.join((candidate(60, selection=4, score_ratio=6, fund_ratio=.7,
                                  active=active), candidate(79, **upper)))

    def test_labels_only_score_same_screen_and_real_interval_controls(self):
        for labels, outcome in [('0:60:64', 'unexpected_upper_pitch'),
                                ('0:60:64,1:79:128', 'expected_upper_pitch'),
                                ('', 'unlabeled_gap')]:
            r = analyze_calibrated_harmonic_admission(stream(
                frame(100), frame(200, labels, candidates=self.pair())))
            self.assertEqual(r['observations'], {'starting': {outcome: 1}})
            self.assertEqual(r['active_starts'], {})
            self.assertEqual(r['controls'].get('labeled_plus19_pair_frames', 0),
                             int(outcome == 'expected_upper_pitch'))

    def test_start_is_counted_once_using_prior_state_and_initial_state_unknown(self):
        r = analyze_calibrated_harmonic_admission(stream(
            frame(100, '0:60:64', candidates=self.pair()),
            frame(200, '0:60:64', candidates=self.pair(1)),
            frame(300, '0:60:64', candidates=self.pair(1))))
        self.assertEqual(r['observations']['initial_state_unknown'], {'unexpected_upper_pitch': 1})
        self.assertEqual(r['observations']['established'], {'unexpected_upper_pitch': 1})
        self.assertEqual(r['active_starts'], {'starting': {'unexpected_upper_pitch': 1}})
        self.assertEqual(r['examples']['unexpected_upper_pitch'][0]['sample'], 200)

    def test_quiet_strong_upper_noncalibrated_and_ineligible_lanes_excluded(self):
        for changes in ({'score_ratio': 1.1}, {'cal_direct': 0},
                        {'selection': 5}, {'playable_mask': 128}):
            r = analyze_calibrated_harmonic_admission(stream(
                frame(100, candidates=self.pair(upper_changes=changes))))
            self.assertEqual(r['observations'], {})
        r = analyze_calibrated_harmonic_admission(stream(
            frame(100, candidates=self.pair(), quiet=1)))
        self.assertEqual(r['observations'], {})

    def test_fundamental_relation_uses_energy_not_share_alone(self):
        r = analyze_calibrated_harmonic_admission(stream(
            frame(100), frame(200, candidates=self.pair(1))))
        example = r['examples']['unlabeled_gap'][0]
        self.assertAlmostEqual(example['fundamental_ratio'], .4 * .98 / (6 * .7))

    def test_aggregate_and_order_mismatches_fail(self):
        row = frame(100, '0:60:64')
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            analyze_calibrated_harmonic_admission(stream(row, row))
        expected = dict(labeled=1, matched=1, false_positive_voices=0,
                        false_wrong_note_voices=0, false_wrong_string_voices=0, false_gap_voices=0)
        with self.assertRaisesRegex(ValueError, 'trace/report mismatch for matched'):
            analyze_calibrated_harmonic_admission(stream(row), expected)


class FretReliefTests(unittest.TestCase):
    def option(self, **changes):
        features = dict(note=44, selection=3, local=1, playable_mask=3,
                        selector_pool_member=1, selector_raw_score=.22,
                        selector_best_adjusted_score=-.02, selector_option_mask=3,
                        selector_open_count=2)
        features.update(changes)
        return candidate(**features)

    def test_realistic_overtones_do_not_disqualify_fundamental_support(self):
        # Equal energy in the fundamental and two upper partials. The native
        # weighted total is 1 + .72 + .55, so support is real but below one.
        share = 1 / (1 + .72 + .55)
        for gain_squared in (.01, 1, 100):
            with self.subTest(gain_squared=gain_squared):
                scaled_share = gain_squared / (gain_squared * (1 + .72 + .55))
                r = analyze_fret_relief(stream(frame(100, '0:44:2', candidates=self.option(
                    fund_ratio=scaled_share))))
                self.assertAlmostEqual(scaled_share, share)
                self.assertEqual({p['evidence'] for p in r['probes']},
                                 {'direct_local_native_fundamental'})

    def test_native_fundamental_floor_is_not_an_independent_classifier(self):
        for share, expected in ((.199, 'other'), (.2, 'direct_local_native_fundamental'),
                                (1, 'direct_local_native_fundamental')):
            with self.subTest(share=share):
                r = analyze_fret_relief(stream(frame(100, '0:44:2', candidates=self.option(
                    fund_ratio=share))))
                self.assertEqual({p['evidence'] for p in r['probes']}, {expected})

    def test_small_relief_opens_shorter_fret_before_deeper_wrong_string(self):
        result = analyze_fret_relief(stream(frame(100, '0:44:2', candidates=self.option())))
        by_cap = {p['cap']: p['outcomes'] for p in result['probes']}
        self.assertEqual(by_cap[.025], {'expected_options_only_with_missing_lane': 1})
        self.assertEqual(by_cap[.05], {'mixed_expected_and_wrong_string_options': 1})
        self.assertEqual(result['totals']['reconstructed_observations'], 1)

    def test_labels_and_tracking_do_not_gate_the_screen(self):
        a = analyze_fret_relief(stream(frame(100, '0:44:2', candidates=self.option())))
        b = analyze_fret_relief(stream(frame(100, candidates=self.option(
            active=1, phase_valid=1, onset=8, age=99, assigned_mask=1))))
        self.assertEqual(a['deficit_bins'], b['deficit_bins'])
        self.assertEqual([sum(p['outcomes'].values()) for p in a['probes']],
                         [sum(p['outcomes'].values()) for p in b['probes']])
        self.assertTrue(all(p['outcomes'] == {'unlabeled_gap_candidate': 1} for p in b['probes']))

    def test_quiet_atomic_positive_and_capture_exceptions_are_excluded(self):
        for fields, quiet in [({}, 1), ({}, 2), ({'selector_positive_mask': 3}, 0),
                              ({'selector_pool_member': 0}, 0), ({'direct': 0}, 0),
                              ({'score_ratio': .199}, 0), ({'local': 0}, 0),
                              ({'selection': 4}, 0), ({'selector_raw_score': 0}, 0)]:
            with self.subTest(fields=fields, quiet=quiet):
                r = analyze_fret_relief(stream(frame(100, candidates=self.option(**fields), quiet=quiet)))
                self.assertEqual(r['probes'], [])

    def test_reconstruction_failures_and_impossible_frets_are_separate(self):
        for fields, reason in [({'selector_best_adjusted_score': -.01}, 'score_reconstruction_mismatch'),
                               ({'selector_open_count': 1}, 'score_reconstruction_mismatch'),
                               ({'selector_option_mask': 8}, 'invalid_option_mask'),
                               ({'note': 80}, 'invalid_fret')]:
            with self.subTest(fields=fields):
                r = analyze_fret_relief(stream(frame(100, candidates=self.option(**fields))))
                self.assertEqual(r['exclusions'], {reason: 1})
                self.assertEqual(r['probes'], [])

    def test_zero_at_boundary_is_not_a_positive_option(self):
        r = analyze_fret_relief(stream(frame(100, '0:44:2', candidates=self.option(
            selector_raw_score=.215, selector_best_adjusted_score=-.025))))
        self.assertEqual([p['cap'] for p in r['probes']], [.05])

    def test_expected_wrong_note_wrong_string_and_untyped_are_distinct(self):
        rows = [frame(100, '0:48:2', candidates=self.option()),
                frame(200, '0:44:1', candidates=self.option()),
                frame(300, '0:44:0', candidates=self.option()),
                frame(400, '0:44:2', '0', '44:44:1:0:10:1:0:0', self.option())]
        r = analyze_fret_relief(stream(*rows))
        p = next(p for p in r['probes'] if p['cap'] == .025)
        self.assertEqual(p['outcomes'], {'unexpected_pitch': 1, 'wrong_string_options_only': 1,
                         'expected_pitch_string_unspecified': 1,
                         'expected_options_only_already_rendered': 1})

    def test_high_note_penalty_applies_with_fewer_than_two_open_notes(self):
        r = analyze_fret_relief(stream(frame(100, '0:64:128', candidates=self.option(
            note=64, playable_mask=128, selector_option_mask=128,
            selector_raw_score=.20, selector_open_count=0))))
        self.assertEqual(r['probes'][0]['register'], 'high')
        self.assertEqual(r['probes'][0]['topology'], 'single_option')

    def test_full_output_totals_and_schema_are_verified(self):
        row = frame(100, '0:44:2', voices='45:45:1:1:1:0:0:0', candidates=self.option())
        expected = dict(labeled=1, matched=0, false_positive_voices=1,
                        false_wrong_note_voices=1, false_wrong_string_voices=0, false_gap_voices=0)
        analyze_fret_relief(stream(row), expected)
        with self.assertRaisesRegex(ValueError, 'trace/report mismatch'):
            analyze_fret_relief(stream(row), dict(expected, matched=1))
        for fields in ({'max_fret': 12}, {'selector_margin': .02}):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'baseline'):
                analyze_fret_relief(stream(row), expected | fields)
        for bad in [io.StringIO('# m3_candidate_outcome_v1\n' + HEADER + row),
                    stream(frame(100, candidates=':'.join(self.option().split(':')[:len(CANDIDATE_FIELDS_V1)]))),
                    stream(row, row), stream(frame(100, '0:44:256'))]:
            with self.subTest(), self.assertRaises(ValueError):
                analyze_fret_relief(bad)


class CandidatePopulationTests(unittest.TestCase):
    def test_fundamental_bins_and_probes_use_fractional_energy_share(self):
        r = analyze_candidate_population(stream(frame(100, '0:40:1', candidates=candidate(
            local=1, fund_ratio=1 / (1 + .72 + .55), cal_mask=3))))
        self.assertEqual(r['feature_population']['weak/fundamental/<0.5'],
                         {'expected_pitch_best_string_agrees': 1})
        self.assertEqual(r['rule_population']['weak/fundamental_share_ge_020'],
                         {'expected_pitch_best_string_agrees': 1})
        self.assertFalse(any('ge_1' in key for key in r['rule_population']))

    def test_unselected_candidates_count_without_output_conditioning(self):
        before = frame(100, '0:40:1', candidates=candidate(local=1, cal_mask=3))
        after = frame(100, '0:40:1', voices='40:40:0:0:10:1:0:0',
                      candidates=candidate(local=1, cal_mask=3, selection=4,
                          active=1, assigned_mask=1, rescue_mask=1, phase_valid=1,
                          phase_cents=42, onset=8, fine_mask=7, shadow_kind=4))
        a = analyze_candidate_population(stream(before))
        b = analyze_candidate_population(stream(after))
        self.assertEqual(a, b)
        self.assertEqual(a['totals']['candidate_observations'], 1)
        self.assertEqual(a['label_coverage']['unmatched/weak'], 1)
        self.assertEqual(a['rule_population']['weak/all'],
                         {'expected_pitch_best_string_agrees': 1})

    def test_capture_floor_and_direct_population_are_reapplied(self):
        rows = ','.join([candidate(40, local=1, score_ratio=.199),
                         candidate(41, local=1, direct=0, selection=4),
                         candidate(42, local=0, evidence=0, active=1),
                         candidate(43, evidence=1, score_ratio=.2)])
        result = analyze_candidate_population(stream(frame(100, '0:40:1', candidates=rows)))
        self.assertEqual(result['totals']['candidate_observations'], 1)
        self.assertEqual(result['rule_population']['weak/all'], {'unexpected_pitch': 1})
        self.assertEqual(result['label_coverage']['absent'], 1)

    def test_pitch_string_feasibility_and_gaps_are_separate(self):
        result = analyze_candidate_population(stream(
            frame(100, '0:40:6', candidates=candidate(local=1, cal_mask=7, playable_mask=7)),
            frame(200, '0:40:6', candidates=candidate(local=1, cal_mask=7, playable_mask=7, best_string=2)),
            frame(300, '0:40:6', candidates=candidate(local=1, cal_mask=0)),
            frame(400, '0:40:6', candidates=candidate(local=1, playable_mask=1)),
            frame(500, '0:40:0', candidates=candidate(local=1)),
            frame(600, candidates=candidate(local=1))))
        expected = {'expected_pitch_best_string_disagrees': 1,
                    'expected_pitch_best_string_agrees': 1,
                    'expected_pitch_no_calibrated_string': 1,
                    'expected_pitch_fret_infeasible': 1,
                    'expected_pitch_string_unspecified': 1,
                    'unlabeled_gap_candidate': 1}
        self.assertEqual(result['rule_population']['weak/all'], expected)
        self.assertEqual(result['label_coverage']['best_string_agrees'], 1)
        self.assertEqual(result['totals']['labeled'], 5)
        self.assertEqual(result['totals']['candidate_observations'], 6)

    def test_persistence_resets_on_absence_and_rules_do_not_use_labels(self):
        rows = [frame(i*100, '0:40:1', candidates=candidate(local=1,
                    best_cal=.97, second_cal=.8, cal_mask=3)) for i in range(1, 11)]
        rows += [frame(1100), frame(1200, candidates=candidate(local=1))]
        result = analyze_candidate_population(stream(*rows))
        self.assertEqual(result['rule_population']['weak/persistent_10'],
                         {'expected_pitch_best_string_agrees': 1})
        no_labels = [frame(i*100, candidates=candidate(local=1,
                        best_cal=.97, second_cal=.8, cal_mask=3)) for i in range(1, 11)]
        other = analyze_candidate_population(stream(*no_labels))
        self.assertEqual(other['rule_population']['weak/persistent_10'],
                         {'unlabeled_gap_candidate': 1})
        self.assertEqual(other['rule_population']['weak/calibration_ge_095_margin_ge_010'],
                         {'unlabeled_gap_candidate': 10})

    def test_label_coverage_and_report_alignment_fail_closed(self):
        row = frame(100, '0:40:1,1:44:2', '0', candidates=candidate(local=1, score_ratio=1))
        result = analyze_candidate_population(stream(row), {'labeled': 2, 'matched': 1})
        self.assertEqual(result['label_coverage'],
                         {'present': 1, 'strong': 1, 'fret_feasible': 1,
                          'absent': 1, 'unmatched/absent': 1})
        with self.assertRaisesRegex(ValueError, 'trace/report mismatch'):
            analyze_candidate_population(stream(row), {'labeled': 1, 'matched': 1})
        for bad in [frame(100, '0:128:1'), frame(100, '0:40:256'),
                    frame(100, '0:40:1,0:40:2'), frame(100, candidates=candidate(local=1, best_cal='nan'))]:
            with self.subTest(), self.assertRaises(ValueError):
                analyze_candidate_population(stream(bad))
        with self.assertRaises(ValueError):
            analyze_candidate_population(stream(row, row))


class LabelFailureTests(unittest.TestCase):
    def test_legacy_selector_evidence_is_unknown_not_zero(self):
        c = ':'.join(candidate(selection=3, score_ratio=1).split(':')[:len(CANDIDATE_FIELDS_V1)])
        old = io.StringIO('# m3_candidate_outcome_v1\n' + HEADER +
                         frame(100, '0:40:1', candidates=c))
        result = analyze_label_failures(old)
        self.assertEqual(result['strong_eviction_selector'], [dict(
            cause='not_measured', dp_voice_count=-1, open_count=-1, frames=1)])

    def test_selector_penalties_and_occupied_positive_options_are_separate(self):
        base = dict(selection=3, score_ratio=2, selector_voice_count=2,
                    selector_open_count=1, selector_pool_member=1)
        rows = [frame(i*100, '0:40:1', candidates=candidate(**(base | fields)))
                for i, fields in enumerate([
                    dict(selector_pool_member=0),
                    dict(selector_raw_score=.1, selector_best_adjusted_score=-.1),
                    dict(selector_positive_mask=3, selector_used_mask=1),
                    dict(selector_positive_mask=3, selector_used_mask=3),
                ], 1)]
        result = analyze_label_failures(stream(*rows))
        self.assertEqual(result['strong_eviction_selector'], [dict(
            cause=cause, dp_voice_count=2, open_count=1, frames=1) for cause in (
                'no_positive_option', 'not_pooled', 'positive_free_option',
                'positive_options_occupied')])
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            analyze_label_failures(stream(frame(100, '0:40:1', candidates=candidate(
                selector_best_adjusted_score='nan'))))

    def test_strong_eviction_joint_uses_selection_not_rendered_voice_count(self):
        c = ','.join([candidate(selection=3, score_ratio=1),
                      candidate(44, selection=4), candidate(48, selection=4),
                      candidate(52, selection=5)])
        result = analyze_group_failures(stream(
            frame(100, '0:40:1,1:40:2', candidates=c)))
        self.assertEqual(result['strong_eviction_joint'], [dict(
            true_pitch_count=1, selector_selected_count=2,
            playable_lane_count=2, frames=1)])
        self.assertEqual(result['totals']['labeled'], 2)

    def test_strong_eviction_joint_excludes_weak_spectral_and_rendered_targets(self):
        result = analyze_label_failures(stream(
            frame(100, '0:40:1', candidates=candidate(selection=3, score_ratio=.99)),
            frame(200, '0:40:1', candidates=candidate(selection=2, score_ratio=2)),
            frame(300, '0:40:1', voices='40:40:1:2:10:1:0:0',
                  candidates=candidate(selection=3, score_ratio=2)),
            frame(400, '0:40:1', candidates=candidate(selection=3, score_ratio=2,
                                                      playable_mask=0))))
        self.assertEqual(result['strong_eviction_joint'], [dict(
            true_pitch_count=1, selector_selected_count=0,
            playable_lane_count=0, frames=1)])

    def test_selected_pitch_on_wrong_string_is_assignment_failure(self):
        result = analyze_label_failures(stream(frame(100, '0:40:1',
            voices='40:40:1:2:10:1:0:0', candidates=candidate(selection=4,
                score_ratio=2, active=1, assigned_mask=2, cal_mask=3))))
        self.assertEqual(result['outcomes'], {'wrong_strings_only': 1})
        self.assertEqual(result['feature_outcomes']['selection_strength/selected/strong'],
                         {'wrong_strings_only': 1})
        self.assertEqual(result['feature_outcomes']['assigned/disjoint'], {'wrong_strings_only': 1})
        self.assertEqual(result['totals']['false_wrong_string_voices'], 1)

    def test_rebinned_pitch_is_separate_from_missing_candidate(self):
        result = analyze_label_failures(stream(
            frame(100, '0:40:1', voices='40:41:0:1:10:1:0:0', candidates=candidate(selection=4)),
            frame(200, '0:40:1')))
        self.assertEqual(result['outcomes'], {'no_rendered_pitch': 2})
        self.assertEqual(result['feature_outcomes']['detected_pitch_rebinned/True'], {'no_rendered_pitch': 1})
        self.assertEqual(result['feature_outcomes']['candidate/not_captured'], {'no_rendered_pitch': 1})
        self.assertEqual(result['feature_outcomes']['selection/selected'], {'no_rendered_pitch': 1})

    def test_partial_unison_extra_lanes_and_exact_mask_are_distinct(self):
        one = '40:40:0:0:10:1:0:3'
        both = one + ',40:40:1:0:10:1:0:3'
        result = analyze_label_failures(stream(
            frame(100, '0:40:3', voices=one),
            frame(200, '0:40:1', voices=both),
            frame(300, '0:40:3', '0', voices=both)))
        self.assertEqual(result['outcomes'], {'partial_expected_strings': 1,
                         'expected_strings_plus_extra': 1, 'matched': 1})
        self.assertEqual(result['feature_outcomes']['2_strings/rendered_mask/partial'],
                         {'partial_expected_strings': 1})

    def test_report_counts_and_rendered_matches_are_validated(self):
        row = frame(100, '0:40:1', '0', '40:40:0:0:10:1:0:0')
        expected = dict(labeled=1, matched=1, false_positive_voices=0,
                        false_wrong_note_voices=0, false_wrong_string_voices=0, false_gap_voices=0)
        self.assertEqual(analyze_label_failures(stream(row), expected)['totals']['matched'], 1)
        with self.assertRaisesRegex(ValueError, 'trace/report mismatch'):
            analyze_label_failures(stream(row), dict(expected, labeled=2))
        with self.assertRaisesRegex(ValueError, 'rendered lanes disagree'):
            analyze_label_failures(stream(frame(100, '0:40:1', voices='40:40:0:0:10:1:0:0')))
        with self.assertRaises(ValueError):
            analyze_label_failures(stream(row, row))

    def test_unspecified_string_and_other_candidate_can_match(self):
        result = analyze_label_failures(stream(frame(100, '0:40:0', '0', '39:40:255:0:10:1:0:0')))
        self.assertEqual(result['outcomes'], {'matched': 1})
        self.assertEqual(result['feature_outcomes']['rendered_from_other_candidate/True'], {'matched': 1})

    def test_overlapping_labels_require_one_exact_physical_group(self):
        one = '40:40:0:0:10:1:0:3'
        two = one + ',40:40:1:0:10:1:0:3'
        result = analyze_group_failures(stream(
            frame(100, '0:40:1,1:40:2', '', two),
            frame(200, '0:40:1,1:40:2', '0', one)))
        self.assertEqual(result['totals']['labeled'], 4)
        self.assertEqual(result['totals']['matched'], 1)
        self.assertEqual(result['totals']['covered_label_frames'], 3)
        self.assertEqual(result['totals']['attributed_frames'], 2)
        self.assertEqual(result['totals']['attributed_matches'], 1)
        self.assertEqual(result['outcomes'], {'matched': 1, 'partial_expected_strings': 1})
        self.assertEqual(result['per_pitch_mask'],
                         {'note40/mask3': {'matched': 1, 'partial_expected_strings': 1}})

    def test_overlap_does_not_authorize_unlabeled_extra_string(self):
        voices = '40:40:0:0:10:1:0:7,40:40:1:0:10:1:0:7,40:40:2:2:10:1:0:7'
        result = analyze_group_failures(stream(frame(100, '0:40:1,1:40:2', '', voices)))
        self.assertEqual(result['totals']['covered_label_frames'], 0)
        self.assertEqual(result['outcomes'], {'expected_strings_plus_extra': 1})
        self.assertEqual(result['totals']['false_wrong_string_voices'], 1)

    def test_union_tracks_active_rows_and_label_order(self):
        voice = '40:40:1:0:10:1:0:2'
        a = analyze_group_failures(stream(
            frame(100, '0:40:1,1:40:2', '1', voice),
            frame(200, '1:40:2', '1', voice)))
        b = analyze_group_failures(stream(
            frame(100, '1:40:2,0:40:1', '1', voice),
            frame(200, '1:40:2', '1', voice)))
        self.assertEqual(a['totals'], b['totals'])
        self.assertEqual(a['feature_outcomes'], b['feature_outcomes'])
        self.assertEqual(a['outcomes'], {'partial_expected_strings': 1, 'matched': 1})

    def test_note_only_group_does_not_relax_typed_row_coverage(self):
        result = analyze_group_failures(stream(frame(
            100, '0:40:1,1:40:0', '1',
            '40:40:0:0:10:1:0:3,40:40:1:0:10:1:0:3')))
        self.assertEqual(result['outcomes'], {'matched': 1})
        self.assertEqual(result['totals']['covered_label_frames'], 1)
        self.assertEqual(result['per_pitch_mask'], {'note40/mask0': {'matched': 1}})

    def test_note_only_physical_group_requires_a_physical_lane_like_native(self):
        result = analyze_group_failures(stream(frame(
            100, '0:40:0', '0', '40:40:255:0:10:1:0:0')))
        self.assertEqual(result['totals']['matched'], 1)
        self.assertEqual(result['totals']['attributed_matches'], 0)

    def test_group_totals_are_checked_against_native_when_available(self):
        row = frame(100, '0:40:1,1:40:2', '',
                    '40:40:0:0:10:1:0:3,40:40:1:0:10:1:0:3')
        expected = dict(labeled=2, matched=0, false_positive_voices=0,
                        false_wrong_note_voices=0, false_wrong_string_voices=0,
                        false_gap_voices=0,
                        physical_group_diagnostics=dict(
                            physical_group_labeled='1', physical_group_matched='1'))
        analyze_group_failures(stream(row), expected)
        for key in ('physical_group_labeled', 'physical_group_matched'):
            with self.subTest(key=key):
                bad = dict(expected, physical_group_diagnostics=dict(
                    expected['physical_group_diagnostics'], **{key: '2'}))
                with self.assertRaisesRegex(ValueError, key):
                    analyze_group_failures(stream(row), bad)

    def test_quiet_wait_spectral_evidence_is_separated_from_normal_frames(self):
        result = analyze_group_failures(stream(
            frame(100, '0:40:7', candidates=candidate(score_ratio=2.5, local=1), quiet=2),
            frame(200, '0:40:7', candidates=candidate(score_ratio=.4, local=0))))
        axes = result['feature_outcomes']
        self.assertEqual(axes['3_strings/quiet2/strength/strong'], {'no_rendered_pitch': 1})
        self.assertEqual(axes['3_strings/quiet2/direct_local/1:1'], {'no_rendered_pitch': 1})
        self.assertEqual(axes['3_strings/quiet2/score_ratio/<4'], {'no_rendered_pitch': 1})
        self.assertNotIn('3_strings/quiet2/strength/weak', axes)
        self.assertEqual(axes['3_strings/quiet0/strength/weak'], {'no_rendered_pitch': 1})


if __name__ == '__main__':
    unittest.main()
