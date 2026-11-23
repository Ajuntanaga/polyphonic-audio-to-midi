"""Mock-only screen contracts; no native execution or recording access."""
import unittest

from tests import test_portable_exact_cell_sharing as sharing_tests
from tools.portable_narrow_clear import FLAG, SCHEMA, clear_counts, run


def summary(enabled, quiet=150):
    return (f'm3_replay: narrow_clears enabled={int(enabled)} quiet={quiet} updates=0 '
            f'performed={0 if enabled else quiet} skipped={quiet if enabled else 0}\n')


class NarrowClearTests(unittest.TestCase):
    def exercise(self, **kwargs):
        return sharing_tests.ExactCellSharingTests().exercise(
            runner=run, flag=FLAG, summary=summary, **kwargs)

    def test_fixed_twelve_run_screen_and_counter_identity(self):
        passed, report, error, commands, _ = self.exercise()
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertEqual(report['schema'], SCHEMA)
        self.assertEqual(report['flag'], FLAG)
        self.assertEqual(len(commands), 12)
        self.assertEqual([FLAG in command for command in commands],
                         [False, True, True, False, False, True] * 2)
        for command in commands:
            self.assertNotIn('--diagnostic-exact-cell-sharing', command)
            self.assertNotIn('--diagnostic-packed-cell-update', command)
        for case in report['cases']:
            self.assertTrue(case['raw_midi_bit_identical'])
            self.assertEqual(case['timing_runs']['on']['cell_counts'],
                             dict(quiet_samples=150, updates=0))
        self.assertFalse(report['promotion_accepted'])

    def test_missing_duplicate_wrong_mode_or_unexercised_summary_fails(self):
        for text in ('', summary(True) * 2, summary(False), summary(True, 0),
                     summary(True).replace('updates=0', 'updates=1')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                clear_counts(text, True)

    def test_incomplete_or_wrong_clear_counters_fail(self):
        for enabled, text in (
                (True, summary(True).replace('skipped=150', 'skipped=149')),
                (True, summary(True).replace('performed=0 skipped=150', 'performed=1 skipped=149')),
                (False, summary(False).replace('performed=150 skipped=0', 'performed=149 skipped=1'))):
            with self.subTest(text=text), self.assertRaises(ValueError):
                clear_counts(text, enabled)

    def test_paired_quiet_counts_must_match(self):
        def mutate(index, timing, streams, command, midi):
            if index == 1:
                streams['stderr'].seek(0)
                streams['stderr'].truncate()
                streams['stderr'].write(summary(True, 149))
        _, report, error, commands, _ = self.exercise(mutate_run=mutate)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(len(commands), 2)
        self.assertEqual(report['state'], 'failed')

    def test_one_cpu_loss_rejects_without_repeating_pairs(self):
        def mutate(index, timing, streams, command, midi):
            if index == 5:
                timing['thread_cpu']['total_ns'] = 4100000
        passed, report, error, commands, _ = self.exercise(mutate_run=mutate)
        self.assertIsNone(error)
        self.assertFalse(passed)
        self.assertEqual(len(commands), 12)
        self.assertTrue(report['collection_pass'])
        self.assertFalse(report['usefulness_screen_pass'])


if __name__ == '__main__':
    unittest.main()
