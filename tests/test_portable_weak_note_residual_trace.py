import unittest
from tools.portable_weak_note_residual_trace import summarize

class ResidualSummaryTests(unittest.TestCase):
    def row(self, **changes):
        row = dict(sample='1023', tick='16', note='81', base_notes='55,43',
                   base_valid='1', added_valid='1', expected_note='1', already_emitted='0',
                   residual_gain='0.2', independent_energy='0.1', fundamental_overlap='0.3', score_ratio='0.01')
        row.update(parent_note='69', parent_evidence='1', parent_in_base='0',
                   paired_available='1', paired_base_valid='1', paired_added_valid='1', paired_gain='0.02')
        row.update(changes)
        return row

    def test_invalid_fit_unavailable(self):
        result = summarize([self.row(added_valid='0', residual_gain='nan')], 81, 1000, 2000)
        self.assertEqual(result['jointly_valid'], 0)
        self.assertIsNone(result['residual_gain'])

    def test_weak_candidate_retained(self):
        result = summarize([self.row()], 81, 1000, 2000)
        self.assertEqual(result['score_ratio']['median'], 0.01)
        self.assertEqual(result['expected_rows'], 1)

    def test_bad_capture_rejected(self):
        for rows in ([], [self.row(), self.row()], [self.row(base_notes='81,55')],
                     [self.row(tick='17')], [self.row(sample='2000')],
                     [self.row(residual_gain='nan')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                summarize(rows, 81, 1000, 2000)

    def test_unavailable_pair_is_not_zero_gain(self):
        result = summarize([self.row(paired_available='0', paired_base_valid='0',
                                    paired_added_valid='0', paired_gain='nan')], 81, 1000, 2000)
        self.assertIsNone(result['paired_gain'])
        self.assertEqual(result['paired_available_rows'], 0)

    def test_pair_requires_evidence_and_validity(self):
        for changes in (dict(parent_note='68'), dict(parent_evidence='0'),
                        dict(paired_available='0'), dict(paired_gain='nan')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                summarize([self.row(**changes)], 81, 1000, 2000)
        result = summarize([self.row()], 81, 1000, 2000)
        self.assertEqual(result['paired_gain']['median'], 0.02)
