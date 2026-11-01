import csv
import io
import unittest

from tools.residual_admission_analysis import FIELDS, analyze_stream


def observation(**changes):
    row = dict.fromkeys(FIELDS, 0)
    row.update(sample=40000, tick=1008, note=49, base_count=2,
               used_mask=3, free_mask=4, any_label=1, expected_note=1,
               expected_mask=4, base_valid=1, added_valid=1,
               base_residual=.4, added_residual=.1, residual_gain=.3,
               independent_energy=.2, score_ratio=1.5, fund_ratio=.8,
               direct=1, local=1, calibration_similarity=.9,
               calibration_string=2, base_notes='40,45')
    row.update(changes)
    return row


def analyze(*rows, **capture_changes):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter='\t')
    writer.writeheader()
    writer.writerows(rows)
    stream.seek(0)
    capture = dict(rows=len(rows), truncated=False, decimation=16)
    capture.update(capture_changes)
    return analyze_stream(stream, capture)


class ResidualAdmissionAnalysisTests(unittest.TestCase):
    def test_pitch_and_string_evidence_remain_separate(self):
        result = analyze(
            observation(),
            observation(tick=1024, sample=41000, expected_mask=8),
            observation(tick=1040, sample=42000, expected_mask=0),
            observation(tick=1056, sample=43000, expected_note=0),
            observation(tick=1072, sample=44000, any_label=0, expected_note=0))
        self.assertEqual(result['totals']['eligible'], 5)
        policy = result['policies'][-1]
        self.assertEqual(policy['expected_pitch_samples'], 3)
        self.assertEqual(policy['false_pitch_samples'], 2)
        self.assertEqual(policy['calibrated_wrong_string'], 1)
        self.assertEqual(policy['sole_free_string']['expected_free_string'], 1)
        self.assertFalse(result['production_changed'])

    def test_ambiguous_and_already_emitted_candidates_are_not_promoted(self):
        result = analyze(
            observation(shared_fundamental=1),
            observation(tick=1024, fundamental_overlap=.99),
            observation(tick=1040, already_emitted=1),
            observation(tick=1056, base_count=1, base_notes='40'),
            observation(tick=1072, added_valid=0))
        self.assertEqual(result['totals']['harmonic_ambiguity'], 2)
        self.assertEqual(result['totals']['already_emitted'], 1)
        self.assertEqual(result['totals']['fewer_than_two_base_pitches'], 1)
        self.assertEqual(result['totals']['invalid_fit'], 1)
        self.assertTrue(all(p['expected_pitch_samples'] == 0 for p in result['policies']))

    def test_both_gain_and_independent_energy_are_required(self):
        result = analyze(observation(added_residual=.399, residual_gain=.001,
                                     independent_energy=.0001))
        self.assertEqual(result['policies'][0]['expected_pitch_samples'], 1)
        self.assertEqual(result['policies'][-1]['expected_pitch_samples'], 0)

    def test_invalid_captures_fail_closed(self):
        for capture in (dict(truncated=True), dict(decimation=8), dict(rows=2)):
            with self.subTest(capture=capture), self.assertRaises(ValueError):
                analyze(observation(), **capture)

    def test_invalid_or_inconsistent_evidence_is_rejected(self):
        for change in (dict(free_mask=3), dict(tick=1009), dict(note=128),
                       dict(base_notes='40,40'), dict(residual_gain=.2),
                       dict(independent_energy=float('nan'))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                analyze(observation(**change))
        with self.assertRaises(ValueError):
            analyze(observation(), observation())


if __name__ == '__main__':
    unittest.main()
