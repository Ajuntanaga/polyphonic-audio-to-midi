import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_portable_pending_string_trace as shared
from tests.test_assignment_cost_analysis import cost_row, outcome_row
from tests.test_portable_routing_trace import write_rows
from tools.portable_assignment_trace import digest
from tools import portable_pending_midi_retention_trace as trace


class PendingMidiRetentionTraceTests(unittest.TestCase):
    def execute(self, root, *, drift=None, diagnosis_error=False):
        helper = shared.PortablePendingStringTraceTests()
        args, text = helper.fixture(root)
        path = root / 'saved-outcome.tsv'
        write_rows(path, [outcome_row((42,), sample=s) for s in (63, 127, 191)])
        refs = json.loads(args[3].read_text())
        refs['replay_references']['current-on']['outcome_sha256'] = digest(path)
        args[3].write_text(json.dumps(refs))
        with patch.object(trace, 'CASES', shared.CASES[:2]), patch.object(
                trace, 'window_for', return_value=(0, 192)), patch.object(
                trace, 'compare_anchors', return_value={'observed_anchors': 1},
                side_effect=ValueError('Missing anchor') if diagnosis_error else None) as diagnose:
            calls = helper.execute(args, text, drift=drift, runner=trace.run)
        return args, calls, diagnose

    def test_two_current_on_captures_compare_saved_complete_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            args, calls, diagnose = self.execute(Path(directory))
            self.assertEqual(calls.call_count, 2)
            self.assertEqual(diagnose.call_count, 2)
            for call in calls.call_args_list:
                command = call.args[0]
                self.assertNotIn('--diagnostic-pending-string-reservation', command)
                self.assertNotIn('--diagnostic-pending-midi-retention', command)
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertEqual(report['state'], 'completed')
            self.assertEqual(len(report['runs']), 2)
            for result in report['runs'].values():
                self.assertTrue(result['saved_outcome_bit_identical'])
                self.assertEqual(result['bounded_diagnosis'], {'observed_anchors': 1})

    def test_consistent_outcome_drift_and_missing_diagnosis_fail_closed(self):
        for drift, failure in (('outcome-always', 'saved complete outcome'),
                                (None, 'Missing anchor')):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, failure):
                    self.execute(Path(directory), drift=drift, diagnosis_error=drift is None)
                report = json.loads((Path(directory) / 'output/report.json').read_text())
                self.assertEqual(report['state'], 'failed')
                self.assertTrue(report['final'])

    def compare(self, *, costs=(0, 2), changes=None, missing=False):
        rows = [cost_row(33, ordinal=0, count=2, packed=8, joint=3,
                         costs=(1,), prior=255, active=0),
                cost_row(37, ordinal=1, count=2, primary=1, packed=8, joint=3, costs=costs)]
        for row in rows:
            row.update(prior_attack_ticks='0', attack_required='10', allocation_preview='0')
        if changes:
            rows[0].update(changes)
        if missing:
            rows.pop(0)
        label = dict(label_index=1, midi_note=37)
        frames = [dict(sample=127, candidate_state=dict(best_string=2, cal_mask=7))]
        with patch.object(trace, 'ANCHORS', {1: dict(peer=33, retained_lane=0, samples=(127,))}):
            return trace.compare_anchors(rows, frames, label)['observations'][0]

    def test_omission_preserves_original_bit_positions_and_valid_correction(self):
        forced = self.compare()
        self.assertEqual(forced['original'], dict(cost=3, packed=8, target_lane=1))
        self.assertEqual(forced['omitted'], dict(cost=0, packed=0, target_lane=0))
        correction = self.compare(costs=(5, 2))
        self.assertEqual(correction['omitted'], dict(cost=2, packed=8, target_lane=1))
        self.assertEqual(correction['omitted_pinned_to_retained']['cost'], 5)
        self.assertEqual(correction['best_string'], 2)

    def test_missing_peer_ready_peer_and_corrupt_original_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing target, peer or outcome'):
            self.compare(missing=True)
        for changes in ({'prior_active': '1'}, {'prior_midi': '1'},
                        {'prior_attack_ticks': '9'}, {'playable': '3'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.compare(changes=changes)
        with self.assertRaisesRegex(ValueError, 'Original optimum changed'):
            self.compare(costs=(5, 4))

    def test_window_keeps_one_second_before_annotation(self):
        self.assertEqual(trace.window_for(trace.CASES[0]), (3494592, 3663040))


if __name__ == '__main__':
    unittest.main()
