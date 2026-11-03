import copy
import tempfile
import unittest
from pathlib import Path

from tools.controlled_admission_gate import (
    CASES, FIELDS, TARGET_FIELDS, evaluate_admission, read_target_detail)


def target(matched=40):
    return dict(label_index=0, start_sample=24000, end_sample=244800,
                midi_note=36, string_mask=1, calibration_pass=0,
                labeled=100, matched=matched)


def cases():
    result = {}
    for name in CASES:
        output = {key: '0' for key in FIELDS}
        output.update(labeled='100' if name == 'solo' else '200',
                      matched='40' if name == 'solo' else '80')
        replay = dict(output=output, target=target())
        result[name] = dict(control_identical=True,
                            replays={mode: copy.deepcopy(replay) for mode in ('off', 'on')})
    return result


class ControlledAdmissionGateTests(unittest.TestCase):
    def test_added_note_only_gain_cannot_count_as_target_recovery(self):
        data = cases()
        data['nearby_0dB']['replays']['on']['output']['matched'] = '90'
        result = evaluate_admission(data)
        self.assertTrue(result['aggregate_match_improved'])
        self.assertFalse(result['target_improved'])
        self.assertFalse(result['accepted_for_corpus_screen'])

    def test_aggregate_gain_cannot_hide_target_loss_in_any_case(self):
        for name in CASES[1:]:
            with self.subTest(case=name):
                data = cases()
                nearby = data['nearby_0dB']['replays']['on']
                nearby['target']['matched'], nearby['output']['matched'] = 45, '90'
                changed = data[name]['replays']['on']
                changed['target']['matched'], changed['output']['matched'] = 39, '90'
                result = evaluate_admission(data)
                self.assertIn(name, result['regressions'])
                self.assertFalse(result['accepted_for_corpus_screen'])

    def test_real_target_gain_passes_only_with_every_safety_count_preserved(self):
        data = cases()
        improved = data['nearby_0dB']['replays']['on']
        improved['target']['matched'], improved['output']['matched'] = 45, '85'
        result = evaluate_admission(data)
        self.assertTrue(result['accepted_for_corpus_screen'])
        self.assertEqual(result['cases']['nearby_0dB']['target_matched_delta'], 5)
        for field in FIELDS[1:]:
            with self.subTest(field=field):
                unsafe = copy.deepcopy(data)
                unsafe['solo']['replays']['on']['output'][field] = '1'
                self.assertFalse(evaluate_admission(unsafe)['accepted_for_corpus_screen'])

    def test_missing_target_changed_geometry_and_impossible_counts_fail_closed(self):
        for key, value in (('midi_note', 37), ('string_mask', 2),
                           ('start_sample', 24001), ('labeled', 99),
                           ('matched', 101), ('matched', -1), ('matched', 40.5)):
            with self.subTest(key=key, value=value):
                data = cases()
                data['solo']['replays']['on']['target'][key] = value
                with self.assertRaises(ValueError):
                    evaluate_admission(data)
        data = cases()
        del data['solo']['replays']['on']['target']
        with self.assertRaisesRegex(ValueError, 'missing target'):
            evaluate_admission(data)
        data = cases()
        data['solo']['replays']['on']['output']['matched'] = '39'
        with self.assertRaisesRegex(ValueError, 'counts disagree'):
            evaluate_admission(data)

    def test_missing_case_or_changed_control_cannot_pass(self):
        data = cases()
        data.pop('solo')
        with self.assertRaisesRegex(ValueError, 'all five'):
            evaluate_admission(data)
        data = cases()
        data['solo']['control_identical'] = False
        with self.assertRaisesRegex(ValueError, 'control'):
            evaluate_admission(data)

    def test_parser_selects_exact_target_and_rejects_missing_duplicate_or_bad_rows(self):
        header = '\t'.join((*TARGET_FIELDS, 'extra_diagnostic')) + '\n'

        def line(detail):
            return '\t'.join(str(detail[key]) for key in TARGET_FIELDS) + '\t0:1,1:2\n'

        wanted = line(target())
        added = line(dict(target(), label_index=1, midi_note=49, string_mask=8, matched=70))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'replay.tsv'
            path.write_text('labeled\tmatched\n200\t110\n' + header + added + wanted)
            self.assertEqual(read_target_detail(path), target())
            for text in ('labeled\tmatched\n200\t110\n', header + added,
                         header + wanted * 2, header + '0\t24000\n',
                         header + line(dict(target(), matched=-1))):
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(ValueError):
                        read_target_detail(path)


if __name__ == '__main__':
    unittest.main()
