import unittest
from tools.vst3_stable_note_corpus_gate import compare_component_pitch


def event(sample, kind, voice=0, note=60):
    return dict(sample=sample, kind=kind, voice_id=voice, channel=voice+1,
                note=note, velocity=100 if kind == 'on' else 0)


class CorpusPitchGateTests(unittest.TestCase):
    labels = [dict(label_index=0, start_sample=0, end_sample=80, midi_note=60)]

    def compare(self, before, after):
        return compare_component_pitch(before, after, self.labels, 100)

    def test_continuation_merge_preserves_pitch_but_does_not_prove_articulation(self):
        before = [event(0, 'on'), event(40, 'off'), event(40, 'on', 1), event(80, 'off', 1)]
        after = [event(0, 'on'), event(80, 'off')]
        result = self.compare(before, after)
        self.assertTrue(result['gate_pass'])
        self.assertEqual(result['label_changes'][0]['longest_hold_delta'], 40)
        self.assertEqual(result['acoustic_repluck_preservation'], 'not measured')
        self.assertFalse(result['promotion_accepted'])

    def test_lost_unison_rejects_even_with_identical_pitch_presence(self):
        before = [event(0, 'on'), event(0, 'on', 1), event(80, 'off'), event(80, 'off', 1)]
        result = self.compare(before, [event(0, 'on'), event(80, 'off')])
        self.assertTrue(result['gates']['no_label_pitch_loss'])
        self.assertFalse(result['gates']['pitch_multiplicity_identical'])
        self.assertFalse(result['gate_pass'])

    def test_gap_extension_rejected(self):
        result = self.compare([event(0, 'on'), event(80, 'off')],
                              [event(0, 'on'), event(90, 'off')])
        self.assertFalse(result['gates']['no_false_output_growth'])
        self.assertFalse(result['gate_pass'])

    def test_missing_release_is_visible(self):
        result = self.compare([event(0, 'on'), event(80, 'off')], [event(0, 'on')])
        self.assertFalse(result['gates']['eof_open_notes_identical'])

    def test_invalid_order_rejected(self):
        with self.assertRaises(ValueError):
            self.compare([event(30, 'on'), event(20, 'off')], [])

    def test_duplicate_labels_rejected(self):
        with self.assertRaises(ValueError):
            compare_component_pitch([], [], self.labels * 2, 100)

    def test_negative_sample_rejected(self):
        with self.assertRaises(ValueError):
            self.compare([event(-1, 'on')], [])
