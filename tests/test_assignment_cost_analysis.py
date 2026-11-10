import unittest

from tools.assignment_cost_analysis import INTEGER_FIELDS, summarize_costs
from tools.candidate_outcome_analysis import CANDIDATE_FIELDS


def cost_row(note=37, *, ordinal=0, count=1, primary=0, packed=0, joint=0,
             costs=(0, 2), prior=0, active=1, sample=127):
    row = dict.fromkeys(INTEGER_FIELDS, '0')
    terms = [[value, 0, 0, 0, 0, 0, 0] for value in costs]
    terms += [[0] * 7 for _ in range(8 - len(terms))]
    row.update(sample=str(sample), tick=str((sample + 1) // 64), note=str(note),
        observed='1', valid='1', selected_count=str(count), ordinal=str(ordinal),
        playable=str((1 << len(costs)) - 1), prior_primary=str(prior),
        prior_active=str(active), prior_mask=str(1 << prior if prior < 8 else 0),
        dp_primary=str(primary), joint_strings=str(packed), joint_cost=str(joint),
        final_primary=str(primary), final_mask=str(1 << primary),
        lane_terms=','.join(':'.join(map(str, lane)) for lane in terms),
        lane_totals=','.join(str(sum(lane)) for lane in terms))
    return row


def outcome_row(notes=(37,), *, sample=127):
    candidates = []
    for note in notes:
        fields = dict.fromkeys(CANDIDATE_FIELDS, '0')
        fields.update(note=str(note), selection='4', active='1')
        candidates.append(':'.join(fields.values()))
    return dict(sample=str(sample), tick=str((sample + 1) // 64), quiet='0',
                signal_samples='64', labels='', matched_labels='', voices='',
                candidates=','.join(candidates))


class AssignmentCostAnalysisTests(unittest.TestCase):
    def summarize(self, rows):
        return summarize_costs(rows, [outcome_row([int(row['note']) for row in rows])],
                               note=37, start=64, end=128)

    def joint(self, peer_costs=(0, 10)):
        return [cost_row(33, ordinal=0, count=2, packed=8, joint=2,
                         costs=peer_costs, prior=255, active=0),
                cost_row(37, ordinal=1, count=2, primary=1, packed=8, joint=2)]

    def test_pending_peer_changes_global_optimum_despite_targets_cheaper_prior_lane(self):
        result = self.summarize(self.joint())
        switch = result['switches'][0]
        self.assertEqual(switch['reason'], 'lower_total_joint_cost')
        self.assertEqual(switch['prior_constrained_cost'], 10)
        self.assertEqual(switch['prior_constraint_extra_cost'], 8)
        self.assertEqual(switch['peers'][0]['prior_active'], 0)
        self.assertTrue(result['native_joint_decisions_reproduced'])

    def test_peer_with_only_one_string_makes_old_target_string_infeasible(self):
        switch = self.summarize(self.joint((0,)))['switches'][0]
        self.assertEqual(switch['reason'], 'prior_string_infeasible_for_complete_joint_assignment')
        self.assertIsNone(switch['prior_constrained_cost'])

    def test_equal_cost_uses_packed_string_tie_break(self):
        switch = self.summarize([cost_row(costs=(0, 0), prior=1)])['switches'][0]
        self.assertEqual(switch['reason'], 'equal_cost_packed_string_tie_break')
        self.assertEqual(switch['prior_constraint_extra_cost'], 0)

    def test_signed_retention_is_added_in_order(self):
        row = cost_row(costs=(3, 1), primary=1, packed=1, joint=1)
        terms = row['lane_terms'].split(',')
        terms[0] = '10:0:0:0:0:0:-7'
        row['lane_terms'] = ','.join(terms)
        switch = self.summarize([row])['switches'][0]
        self.assertEqual(switch['prior_constraint_extra_cost'], 2)

    def test_missing_peer_and_missing_tick_are_rejected(self):
        rows = self.joint()
        with self.assertRaisesRegex(ValueError, 'Incomplete selected assignment peers'):
            summarize_costs(rows[1:], [outcome_row((33, 37))], note=37, start=64, end=128)
        with self.assertRaisesRegex(ValueError, 'Incomplete assignment outcome window'):
            summarize_costs([], [], note=37, start=64, end=128)

    def test_corrupted_costs_masks_clocks_and_duplicates_are_rejected(self):
        for field, value in [('joint_cost', '7'), ('joint_strings', '1'),
                             ('tick', '99'), ('ordinal', '1'), ('playable', '256'),
                             ('lane_terms', 'nan'), ('lane_totals', '1,2,0,0,0,0,0,0')]:
            rows = self.joint()
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.summarize(rows)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.summarize([cost_row(), cost_row()])

    def test_empty_frame_is_explicit_and_not_a_measured_assignment(self):
        result = summarize_costs([], [outcome_row(())], note=37, start=64, end=128)
        self.assertEqual(result['empty_selected_frames'], 1)
        self.assertEqual(result['valid_joint_frames'], 0)
        self.assertEqual(result['target_selected_valid_frames'], 0)


if __name__ == '__main__':
    unittest.main()
