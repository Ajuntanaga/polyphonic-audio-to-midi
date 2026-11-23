import unittest

from tools.complex_attack_baseline import event_identity, event_record, score_fixture


class AttackClockContracts(unittest.TestCase):
    def ev(self, sample, nominal=None):
        return event_record(sample - 10, 10, 10, sample if nominal is None else nominal, 123)

    def score(self, events):
        return score_fixture(events, [100, 300], [120, 320], [180, 380], 1000, 500)

    def test_causal_not_backdated_clock(self):
        r = self.score([self.ev(150), self.ev(390, 330)])
        self.assertFalse(r['fixed_screen_pass'])
        self.assertEqual(r['copies'][1]['headroom_to_baseline_samples'], -10)

    def test_known_two_copy_pass(self):
        r = self.score([self.ev(150), self.ev(350)])
        self.assertTrue(r['fixed_screen_pass'])
        self.assertEqual(r['copies'][1]['first_delay_from_marker_ms'], 30)

    def test_extra_late_cue_fails(self):
        self.assertFalse(self.score([self.ev(150), self.ev(350), self.ev(450)])['fixed_screen_pass'])

    def test_missing_second_fails(self):
        self.assertFalse(self.score([self.ev(150)])['fixed_screen_pass'])

    def test_insertion_boundary_cannot_observe_copy(self):
        r = self.score([self.ev(150), self.ev(300)])
        self.assertEqual(r['copies'][1]['cue_count'], 0)
        self.assertFalse(r['fixed_screen_pass'])

    def test_prefix_compares_delivery_not_nominal(self):
        events = [self.ev(150), self.ev(350, 280)]
        self.assertEqual(len(event_identity(events, 300)), 1)
        other = [dict(e, call_ns=999) for e in events]
        self.assertEqual(event_identity(events, 300), event_identity(other, 300))

    def test_pre_insertion_false_cue_fails(self):
        self.assertFalse(self.score([self.ev(50), self.ev(150), self.ev(350)])['fixed_screen_pass'])

    def test_last_partial_hop_not_backdated(self):
        e = event_record(490, 10, 3, 480, 10)
        self.assertEqual((e['available_sample'], e['padded_samples']), (500, 7))

    def test_padding_event_still_extra(self):
        e = event_record(490, 16, 10, 480, 10)
        self.assertFalse(self.score([self.ev(150), self.ev(350), e])['fixed_screen_pass'])

    def test_invalid_geometry_fails(self):
        with self.assertRaises(ValueError):
            score_fixture([], [100], [120], [], 1000, 500)
        with self.assertRaises(ValueError):
            event_record(0, 10, 11, 0, 0)

    def test_duplicate_event_fails(self):
        with self.assertRaises(ValueError):
            self.score([self.ev(150), self.ev(150)])


if __name__ == '__main__':
    unittest.main()
