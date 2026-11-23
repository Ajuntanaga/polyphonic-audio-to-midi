"""Mock-only runner checks: no native execution or recording access."""
import unittest

from tests import test_portable_exact_cell_sharing as sharing_tests
from tools.portable_packed_cell_update import FLAG, SCHEMA, cell_counts, run


def summary(enabled):
    return f'm3_replay: packed_cell_update enabled={int(enabled)} supported=1 cells=245 guards=12\n'


class PackedCellUpdateTests(unittest.TestCase):
    def exercise(self, **kwargs):
        return sharing_tests.ExactCellSharingTests().exercise(
            runner=run, flag=FLAG, summary=summary, **kwargs)

    def test_fixed_twelve_run_screen_uses_only_packed_flag(self):
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
        for case in report['cases']:
            self.assertTrue(case['raw_midi_bit_identical'])
            self.assertEqual(case['timing_runs']['on']['cell_counts'], dict(cells=245, guards=12))
        self.assertFalse(report['promotion_accepted'])

    def test_missing_duplicate_wrong_mode_or_unsupported_summary_fails(self):
        for text in ('', summary(True) * 2, summary(False),
                     summary(True).replace('supported=1', 'supported=0'),
                     summary(True).replace('cells=245', 'cells=0'),
                     summary(True).replace('guards=12', 'guards=0')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                cell_counts(text, True)

    def test_paired_counts_must_match(self):
        def mutate(index, timing, streams, command, midi):
            if index == 1:
                streams['stderr'].seek(0)
                streams['stderr'].truncate()
                streams['stderr'].write(summary(True).replace('cells=245', 'cells=244'))
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
