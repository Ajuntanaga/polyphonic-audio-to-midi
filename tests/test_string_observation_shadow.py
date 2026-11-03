import copy
import unittest

from tools.string_observation_shadow import analyze, compare_frame, proposals, score, solve, terms


def make_row(note=40, ordinal=0, count=2, costs=(0, 1, 2), likelihood=(0, 3, 1)):
    all_costs = costs + (0,) * (8 - len(costs))
    ll = likelihood + (0,) * (8 - len(likelihood))
    return dict(sample='1023', tick='16', note=str(note), ordinal=str(ordinal),
                observed='1', fixed_context='0', selected_count=str(count),
                isolated='0', prior_committed='0', prior_mask='0', spectral_proposal='0',
                complete_calibration='1', posterior_observation_available='1',
                posterior_updated='1', use_posterior='0', playable='7',
                reserved_coasting='0', reserved_extras='0', valid='1',
                lane_terms=','.join(f'{x}:0:0:0:0:0:0' for x in all_costs),
                posterior_log_likelihood=','.join(map(str, ll)),
                expected_note='1', expected_mask='2', rendered_mask='1')


def decision(*rows):
    rows = list(rows)
    solution = solve([terms(r['lane_terms']) for r in rows],
                     [int(r['playable']) for r in rows],
                     int(rows[0]['reserved_coasting']) | int(rows[0]['reserved_extras']))
    for i, row in enumerate(rows):
        row.update(joint_cost=str(solution[0] if solution else 0),
                   joint_strings=str(solution[1] if solution else 0),
                   dp_primary=str((solution[1] >> (3 * i)) & 7 if solution else 8),
                   valid=str(int(solution is not None)))
    return rows


class ObservationShadowTests(unittest.TestCase):
    def test_joint_solver_conflicts_reservations_and_ties(self):
        zeros = ((0,) * 7,) * 8
        self.assertEqual(solve([zeros, zeros], [3, 3], 0), (0.0, 1))
        self.assertIsNone(solve([zeros, zeros], [3, 3], 1))
        self.assertEqual(solve([zeros], [7], 3), (0.0, 2))

    def test_sequential_cost_terms_preserve_native_rounding(self):
        costs = ((1e16, 0, -1e16, 1, 0, 0, 0),) * 8
        first = ((1, 0, 0, 0, 0, 0, 0),) * 8
        self.assertEqual(solve([first, costs], [1, 2], 0), (1.0, 8))

    def test_baseline_reconstructed_before_shadow_and_mismatch_rejected(self):
        rows = decision(make_row(), make_row(note=44, ordinal=1, costs=(4, 0, 3)))
        self.assertEqual(compare_frame(rows)['availability'], 'reconstructed')
        for row in rows:
            row['joint_cost'] = '99'
        self.assertEqual(compare_frame(rows)['availability'], 'native_dp_mismatch')

    def test_missing_selected_rows_and_native_infeasibility_are_unavailable(self):
        rows = decision(make_row(), make_row(note=44, ordinal=1))
        self.assertEqual(compare_frame(rows[:1])['availability'], 'incomplete_selected_rows')
        for row in rows:
            row['playable'] = '1'
        rows = decision(*rows)
        self.assertEqual(compare_frame(rows)['availability'], 'native_dp_infeasible')

    def test_labels_and_render_state_do_not_influence_proposals(self):
        rows = decision(make_row(), make_row(note=44, ordinal=1, costs=(4, 0, 3)))
        first = compare_frame(rows)
        other = copy.deepcopy(rows)
        for row in other:
            row.update(expected_note='0', expected_mask='128', rendered_mask='255',
                       candidate_age_ticks='99999', group_after='255', midi_mask='255')
        second = compare_frame(other)
        self.assertEqual(first['shadow_packed'], second['shadow_packed'])
        self.assertEqual(first['reasons'], second['reasons'])

    def test_committed_owner_and_recorded_groups_remain_frozen(self):
        for field, value in [('prior_committed', '1'), ('prior_mask', '3'),
                             ('spectral_proposal', '3')]:
            rows = decision(make_row(likelihood=(0, 10, 0)),
                            make_row(note=44, ordinal=1, costs=(4, 0, 3)))
            rows[0][field] = value
            result = compare_frame(rows)
            self.assertEqual(result['shadow_packed'] & 7, result['baseline_packed'] & 7)
            self.assertNotEqual(result['reasons'][0], None)
        for position, amount in [(5, -512), (6, -1024)]:
            row = make_row()
            lanes = [list(v) for v in terms(row['lane_terms'])]
            lanes[0][position] = amount
            changed, masks, reasons = proposals([row], [lanes], 0)
            self.assertEqual(masks, [1])
            self.assertIsNotNone(reasons[0])

    def test_infeasible_likelihood_mask_and_nonfinite_cost_refused(self):
        rows = decision(make_row(note=32), make_row(note=44, ordinal=1))
        with self.assertRaisesRegex(ValueError, 'fret mask'):
            compare_frame(rows)
        with self.assertRaisesRegex(ValueError, 'finite'):
            terms('nan:0:0:0:0:0:0,' + ','.join(['0:0:0:0:0:0:0'] * 7))

    def test_earlier_candidate_cannot_take_later_frozen_lane(self):
        rows = decision(make_row(likelihood=(0, 10, 0)),
                        make_row(note=44, ordinal=1, costs=(4, 0, 3)))
        rows[1]['prior_committed'] = '1'
        result = compare_frame(rows)
        self.assertEqual((result['baseline_packed'] >> 3) & 7, 1)
        self.assertEqual((result['shadow_packed'] >> 3) & 7, 1)
        self.assertNotEqual(result['shadow_packed'] & 7, 1)

    def test_downstream_rescue_is_not_a_new_gain(self):
        row = make_row(); row['rendered_mask'] = '2'
        result = score(row, 0, 1)
        self.assertEqual(result['dp_corrected'], 1)
        self.assertEqual(result['already_rendered_correction_not_new_gain'], 1)
        self.assertEqual(result['render_absent_correction_opportunity'], 0)
        result = score(row, 0, 2)
        self.assertEqual(result['downstream_rescued_row_put_at_risk'], 1)
        result = score(row, 1, 2)
        self.assertEqual(result['dp_spoiled'], 1)
        row['expected_note'] = '0'
        self.assertEqual(score(row, 0, 1)['unlabeled_changed'], 1)

    def test_trace_clock_count_and_duplicate_checks(self):
        rows = decision(make_row(), make_row(note=44, ordinal=1))
        metadata = dict(sample_count=2048, grid_stride_samples=1024, sampled_frames=2,
                        trace_rows=2, total=dict(targets=3, missing_assignment_row=1))
        report = analyze(rows, metadata)
        self.assertEqual(report['counts']['frames_without_rows'], 1)
        self.assertEqual(report['counts']['missing_annotation_rows'], 1)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            analyze(rows + rows[:1], {**metadata, 'trace_rows': 3})
        with self.assertRaisesRegex(ValueError, 'row count'):
            analyze(rows, {**metadata, 'trace_rows': 3})
        rows[0]['sample'] = '1024'
        with self.assertRaisesRegex(ValueError, 'clock'):
            analyze(rows, metadata)


if __name__ == '__main__':
    unittest.main()
