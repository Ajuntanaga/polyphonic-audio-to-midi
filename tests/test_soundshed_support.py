"""Synthetic interval/clock contracts, no recording or model processing."""
import unittest

from tools.soundshed_support import filter_spans, utility_gate


class SupportContracts(unittest.TestCase):
    def apply(self, current, model=(), native=()):
        return filter_spans(current, model, native, sample_count=2000, sample_rate=1000)

    def test_late_support_does_not_backfill_and_expires_forward(self):
        self.assertEqual(self.apply([(0, 1000, 60)], [(300, 400, 60)]), [(300, 620, 60)])

    def test_model_range_is_inclusive_and_outside_survives(self):
        self.assertEqual(self.apply([(0, 100, n) for n in (34, 35, 88, 89)]),
                         [(0, 100, 34), (0, 100, 89)])

    def test_native_support_is_same_pitch_and_cannot_add_a_voice(self):
        self.assertEqual(self.apply([(500, 800, 42)], native=[(400, 600, 42), (0, 1000, 60)]),
                         [(500, 800, 42)])

    def test_gap_is_not_filled_without_current(self):
        self.assertEqual(self.apply([(10, 20, 60), (50, 60, 60)], [(0, 100, 60)]),
                         [(10, 20, 60), (50, 60, 60)])

    def test_empty_support_cannot_make_notes(self):
        self.assertEqual(self.apply([], [(0, 100, 60)]), [])

    def test_utility_is_conjunction_not_a_tradeoff(self):
        rows = {'ordinary': dict(current_summary=dict(wrong=1000000, gap=500000,
                 present=4000000, expected=10000000), candidate_summary=dict(wrong=800000,
                 gap=250000, present=3990000), budget=dict(budget_screen_pass=True)),
                'extended-middle': dict(budget=dict(budget_screen_pass=True, strict_screen_pass=True))}
        self.assertTrue(utility_gate(rows)['passed'])
        rows['ordinary']['candidate_summary']['present'] -= 1
        self.assertFalse(utility_gate(rows)['passed'])
        rows['ordinary']['candidate_summary']['present'] += 1
        rows['extended-middle']['budget']['budget_screen_pass'] = False
        self.assertFalse(utility_gate(rows)['passed'])


if __name__ == '__main__':
    unittest.main()
