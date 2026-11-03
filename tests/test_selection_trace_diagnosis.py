import unittest

from tools.selection_trace_diagnosis import summarize_selection


def candidate(sample, selection=3):
    return dict(sample=str(sample), tick=str((sample + 1) // 64), note='36',
                selection=str(selection), quiet='0', score_ratio='2', fund_ratio='0.5',
                direct='1', local='1', evidence='1', active='0', phase_valid='1',
                selected_or_coasting='49:4:8:0')


def outcome(sample, pool=0, included=True):
    fields = ['0'] * 42
    fields[0], fields[1], fields[34] = '36', '3', str(pool)
    return dict(sample=str(sample), tick=str((sample + 1) // 64),
                candidates=':'.join(fields) if included else '')


class SelectionTraceDiagnosisTests(unittest.TestCase):
    def test_absent_assignment_can_have_strong_evidence_and_different_selector_paths(self):
        samples = (63, 127, 191)
        measured = summarize_selection(
            [candidate(s) for s in samples],
            [outcome(63), outcome(127, pool=1), outcome(191, included=False)],
            [dict(sample='127', tick='2', note='36')],
            note=36, start=0, end=192, sample_count=192, assignment_stride=64)
        absent = measured['sampled_assignment_absent']
        self.assertEqual(absent['frames'], 2)
        self.assertEqual(absent['positive_flags']['evidence'], 2)
        self.assertEqual(absent['selection'], dict(dp_evicted_not_in_selector_pool=1,
                                                 dp_evicted_pool_not_reported=1))
        self.assertEqual(measured['sampled_assignment_present']['selection'],
                         dict(dp_evicted_in_selector_pool=1))

    def test_missing_candidate_is_refused_instead_of_being_interpreted_as_quiet(self):
        with self.assertRaisesRegex(ValueError, 'incomplete candidate'):
            summarize_selection([candidate(63)], [outcome(63), outcome(127)], [],
                                note=36, start=0, end=128, sample_count=128)

    def test_cross_trace_disagreement_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'disposition mismatch'):
            summarize_selection([candidate(63, selection=4)], [outcome(63)], [],
                                note=36, start=0, end=64, sample_count=64)


if __name__ == '__main__':
    unittest.main()
