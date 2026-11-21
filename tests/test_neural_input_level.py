"""Synthetic causal clocks and occupancy bounds; no recorded audio."""
import unittest
import numpy as np

from tools.neural_input_level import causal_levels, occupancy_by_level, lossless_ceiling, histogram


class InputLevelTests(unittest.TestCase):
    def test_delayed_callback_never_exposes_future_audio(self):
        samples = np.r_[np.zeros(100), np.ones(100)]
        callbacks = [dict(source_end=0, samples=0, started_ns=0, duration_ns=10),
                     dict(source_end=100, samples=100, started_ns=110_000_000, duration_ns=10_000_000),
                     dict(source_end=200, samples=100, started_ns=210_000_000, duration_ns=1)]
        rows = causal_levels(samples, callbacks, 1000)
        self.assertEqual([(r['start'],r['end']) for r in rows], [(0,110),(110,200)])
        self.assertIsNone(rows[0]['power20'])
        self.assertEqual(rows[1]['power_max'], 0)
        callbacks[1]['started_ns'] = 99_000_000
        with self.assertRaises(ValueError): causal_levels(samples, callbacks, 1000)

    def test_trailing_windows_and_startup_denominator(self):
        samples = np.r_[np.ones(20)*.5, np.zeros(81)]
        calls = [dict(source_end=n, samples=20 if n <=100 else 1,
                      started_ns=n*1_000_000, duration_ns=0) for n in (20,40,60,80,100,101)]
        rows = causal_levels(samples, calls, 1000)
        self.assertEqual(rows[1]['power20'], .25)
        self.assertEqual(rows[2]['power20'], 0)
        self.assertEqual(rows[2]['power80'], .125)
        self.assertEqual(rows[4]['power80'], .0625)
        self.assertEqual(rows[5]['power_max'], 0)

    def test_partition_deduplicates_unisons_and_preserves_unknown(self):
        levels = [dict(start=0,end=5,source_end=0,power20=None,power80=None,power_max=None),
                  dict(start=5,end=10,source_end=5,power20=.1,power80=.2,power_max=.2)]
        labels = [dict(start_sample=2,end_sample=8,midi_note=60),
                  dict(start_sample=3,end_sample=7,midi_note=60)]
        spans = [(0,10,60),(1,9,60),(4,9,61)]
        rows = occupancy_by_level(spans,labels,levels,10)
        self.assertEqual({k:sum(r[k] for r in rows) for k in ('genuine','wrong','gap')},
                         dict(genuine=6,wrong=4,gap=5))
        hist = histogram(rows,'power_max')
        self.assertEqual(hist['unknown'],dict(genuine=3,wrong=1,gap=2))

    def test_global_ceiling_uses_weakest_genuine_and_strict_comparison(self):
        rows={'a':[dict(power_max=.1,genuine=10,wrong=5,gap=0),
                   dict(power_max=.05,genuine=0,wrong=0,gap=20),
                   dict(power_max=None,genuine=0,wrong=0,gap=30)],
              'b':[dict(power_max=.05,genuine=1,wrong=0,gap=7),
                   dict(power_max=.01,genuine=0,wrong=0,gap=2)]}
        result=lossless_ceiling(rows,'power_max')
        self.assertEqual(result['threshold_power'],.05)
        self.assertEqual(result['datasets']['a']['gap'],0)
        self.assertEqual(result['datasets']['b']['gap'],2)


if __name__ == '__main__': unittest.main()
