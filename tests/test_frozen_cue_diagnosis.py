import unittest

from tools.frozen_cue_diagnosis import summarize_cues


def traces():
    candidates, outcomes = [], []
    for sample in range(63, 4096, 64):
        selected = 1087 <= sample <= 2047
        stage = 4 if selected else 2
        candidates.append(dict(sample=sample, tick=(sample + 1) // 64, note=36,
            selection=stage, score_ratio=2, fund_ratio=0.6, direct=1, local=0,
            evidence=0, active=int(selected), shadow_kind=0, shadow_interval=127,
            selected_or_coasting='49:4:8:0'))
        fields = ['0'] * 42
        fields[0], fields[1] = '36', str(stage)
        outcomes.append(dict(sample=sample, tick=(sample + 1) // 64,
            candidates=':'.join(fields), labels='0:36:1',
            voices='36:36:0:0:12:1:0:1' if selected else '',
            matched_labels='0' if selected else ''))
    return candidates, outcomes


def measure(candidates, outcomes, intervals=((1024, 2048, 36),)):
    return summarize_cues(candidates, outcomes, intervals, note=36, start=0, end=4096,
                          sample_count=4096)


class FrozenCueDiagnosisTests(unittest.TestCase):
    def test_cue_starts_after_previous_decision_and_expires_before_next(self):
        result = measure(*traces())
        self.assertEqual(result['cue_on']['frames'], 16)
        self.assertEqual(result['cue_on']['target_matched'], 16)
        self.assertEqual(result['cue_off']['target_matched'], 0)
        self.assertEqual(result['cue_on_unmatched']['frames'], 0)
        self.assertEqual(result['cue_off']['admission_prerequisite_failures'],
                         {'fundamental_below_0.85': 48})

    def test_wrong_note_cues_do_not_count_for_target(self):
        result = measure(*traces(), intervals=((1024, 2048, 37),))
        self.assertEqual(result['cue_on']['frames'], 0)
        self.assertEqual(result['all_labeled']['target_matched'], 16)

    def test_incomplete_traces_are_not_treated_as_missing_output(self):
        c, o = traces()
        with self.assertRaisesRegex(ValueError, 'incomplete candidate'):
            measure(c[:-1], o)
        with self.assertRaisesRegex(ValueError, 'incomplete outcome'):
            measure(c, o[:-1])

    def test_wrong_string_label_and_disposition_mismatch_are_rejected(self):
        c, o = traces()
        o[0]['labels'] = '0:36:2'
        with self.assertRaisesRegex(ValueError, 'label identity'):
            measure(c, o)
        c, o = traces()
        c[0]['selection'] = 3
        with self.assertRaisesRegex(ValueError, 'disposition mismatch'):
            measure(c, o)

    def test_overlapping_cues_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cue interval'):
            measure(*traces(), intervals=((1024, 2048, 36), (1536, 2560, 36)))

    def test_missing_outcome_entry_preserves_candidate_evidence(self):
        c, o = traces()
        o[0]['candidates'] = ''
        result = measure(c, o)
        self.assertEqual(result['all_labeled']['positive_flags']['direct'], 64)

    def test_output_failures_are_distinct_and_grouped_by_selection(self):
        c, o = traces()
        o[16]['matched_labels'] = ''
        o[16]['voices'] = '36:36:1:2:12:1:0:2'
        o[17]['matched_labels'] = ''
        o[17]['voices'] = '36:37:0:1:12:1:0:1'
        o[18]['matched_labels'] = ''
        o[18]['voices'] = ''
        result = measure(c, o)['cue_on_unmatched']
        self.assertEqual(result['output'], dict(target_note_string_set_mismatch=1,
            target_detected_but_output_note_changed=1, no_target_voice_output=1))
        self.assertEqual(result['selection_detail']['selected']['output'], result['output'])
        self.assertEqual(result['selection_detail']['selected']['admission_prerequisite_combinations'],
                         {'fundamental_below_0.85': 3})
        self.assertEqual(result['target_output_string_voice_counts'], {'1': 1})
        self.assertEqual(result['target_remapped_note_voice_counts'], {'37': 1})

    def test_native_match_flags_must_agree_with_voice_outputs(self):
        c, o = traces()
        o[16]['voices'] = '36:36:1:2:12:1:0:2'
        with self.assertRaisesRegex(ValueError, 'native match and voice'):
            measure(c, o)

    def test_same_pitch_extra_string_is_not_an_exact_match(self):
        c, o = traces()
        o[16]['voices'] += ',36:36:1:2:12:1:0:2'
        o[16]['matched_labels'] = ''
        result = measure(c, o)['cue_on']
        self.assertEqual(result['target_matched'], 15)
        self.assertEqual(result['output']['target_note_string_set_mismatch'], 1)
        o[16]['matched_labels'] = '0'
        with self.assertRaisesRegex(ValueError, 'native match and voice'):
            measure(c, o)

    def test_group_label_requires_all_and_only_its_strings(self):
        c, o = traces()
        for row in o:
            row['labels'] = '0:36:3'
            if row['voices']:
                row['voices'] += ',36:36:1:0:12:1:0:2'
        result = summarize_cues(c, o, (), note=36, start=0, end=4096,
                                sample_count=4096, string_mask=3)
        self.assertEqual(result['all_labeled']['target_matched'], 16)
        o[16]['voices'] = o[16]['voices'].split(',')[0]
        with self.assertRaisesRegex(ValueError, 'native match and voice'):
            summarize_cues(c, o, (), note=36, start=0, end=4096,
                           sample_count=4096, string_mask=3)

    def test_unconstrained_label_accepts_a_note_without_a_string(self):
        c, o = traces()
        for row in o:
            row['labels'] = '0:36:0'
            if row['voices']:
                row['voices'] = '36:36:255:0:12:1:0:0'
        result = summarize_cues(c, o, (), note=36, start=0, end=4096,
                                sample_count=4096, string_mask=0)
        self.assertEqual(result['all_labeled']['target_matched'], 16)


if __name__ == '__main__':
    unittest.main()
