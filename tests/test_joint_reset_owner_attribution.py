import unittest

from tools.joint_reset_owner_attribution import describe, metrics, pitch_intervals, timeline


def event(sample, kind, note, lane):
    return dict(sample=sample, kind=kind, note=note, voice_id=lane)


class OwnerAttributionTests(unittest.TestCase):
    def test_same_sample_lane_handoff_has_no_empty_interval(self):
        rows = timeline([event(0, 'on', 60, 0), event(5, 'off', 60, 0),
                         event(5, 'on', 60, 1)], 10)
        pitches = pitch_intervals(rows)
        self.assertEqual(pitches[60], [[0, 10]])
        self.assertEqual(metrics(pitches[60], dict(start_sample=2, end_sample=9)),
                         dict(present_samples=7, longest_present_samples=7,
                              present_segments=1, first_present_delay_samples=0))

    def test_other_owner_prevents_output_empty_after_target_off(self):
        rows = timeline([event(0, 'on', 60, 0), event(2, 'on', 48, 1),
                         event(5, 'off', 60, 0)], 15)
        result = describe(rows, pitch_intervals(rows),
                          dict(midi_note=60, start_sample=8, end_sample=12))
        self.assertEqual(result['last_target_disappearance_sample'], 5)
        self.assertEqual(result['minimum_other_owner_count_during_label'], 1)
        self.assertTrue(result['uninterrupted_rendered_ownership_since_anchor'])

    def test_empty_period_and_reappearance_are_clipped(self):
        rows = timeline([event(0, 'on', 60, 0), event(5, 'off', 60, 0),
                         event(10, 'on', 48, 0), event(14, 'on', 60, 1)], 20)
        result = describe(rows, pitch_intervals(rows),
                          dict(midi_note=60, start_sample=8, end_sample=12))
        self.assertEqual(result['empty_output_intervals_since_anchor'], [[5, 10]])
        self.assertEqual(result['empty_output_samples_during_label'], 2)
        self.assertEqual(result['next_target_appearance_sample'], 14)

    def test_unseen_target_anchor_remains_explicit(self):
        rows = timeline([], 20)
        result = describe(rows, {}, dict(midi_note=60, start_sample=8, end_sample=12))
        self.assertIsNone(result['last_target_disappearance_sample'])
        self.assertEqual(result['empty_output_samples_during_label'], 4)

    def test_unison_owners_do_not_double_count_pitch(self):
        rows = timeline([event(1, 'on', 60, 0), event(3, 'on', 60, 1),
                         event(5, 'off', 60, 0), event(8, 'off', 60, 1)], 10)
        self.assertEqual(pitch_intervals(rows)[60], [[1, 8]])

    def test_invalid_pairing_is_not_overwritten(self):
        with self.assertRaises(ValueError):
            timeline([event(1, 'on', 60, 0), event(2, 'on', 62, 0)], 10)


if __name__ == '__main__':
    unittest.main()
