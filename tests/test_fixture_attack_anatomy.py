import json
import os
from pathlib import Path
import unittest

from tools.fixture_attack_anatomy import mean, observation_summary, rise_summary


class SummaryContracts(unittest.TestCase):
    def test_constant_power_has_no_rise(self):
        times = list(range(-100, 201, 5))
        row = rise_summary(times, [0.01] * len(times), 50)
        self.assertAlmostEqual(row['power_ratio'], 1)
        self.assertAlmostEqual(row['before_dbfs'], -20)

    def test_adjacent_window_step(self):
        times = list(range(-100, 201, 5))
        row = rise_summary(times, [1 if t < 0 else 9 for t in times], 30)
        self.assertEqual(row['center_ms'], 0)
        self.assertEqual(row['power_ratio'], 9)

    def test_late_change_is_not_moved_to_first_window(self):
        times = list(range(-100, 501, 5))
        rows = [{'relative_ms': t, 'powers': {'broad': 1 if t < 300 else 16}} for t in times]
        result = observation_summary(rows, {'first': 30, 'late': 335})
        self.assertEqual(result['first']['broad']['power_ratio'], 1)
        self.assertEqual(result['late']['broad']['power_ratio'], 16)
        self.assertEqual(result['late']['broad']['center_ms'], 300)

    def test_zero_is_finite_and_levels_retained(self):
        row = rise_summary(list(range(-100, 101, 5)), [0] * 41, 0)
        self.assertEqual(row['power_ratio'], 1)
        self.assertEqual(row['before_dbfs'], -240)

    def test_invalid_inputs_fail(self):
        for values in ([], [-1], [float('nan')]):
            with self.assertRaises(ValueError):
                mean(values)
        with self.assertRaises(ValueError):
            rise_summary([0, 0], [1, 1], 0)
        with self.assertRaises(ValueError):
            rise_summary([0, 5], [1], 0)


@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true', 'Numerics execute on GitHub only')
class NumericalContracts(unittest.TestCase):
    def test_centered_band_accounting_and_finite_curves(self):
        import numpy as np
        from tools.portable_fixture_attack_anatomy import measure
        spec = json.loads(Path('docs/recovery/fixture-attack-anatomy-20261123.json').read_text())
        rate = spec['sample_rate']
        times = np.arange(spec['samples']) / rate
        signal = 0.1 * np.sin(2 * np.pi * 261.625565 * times)
        rows, spectrum, frequencies, error = measure(signal, rate, 48000, 60, spec['measurement'])
        self.assertEqual(len(rows), 261)
        self.assertEqual((rows[0]['relative_ms'], rows[-1]['relative_ms']), (-100, 1200))
        self.assertEqual(spectrum.shape, (261, len(frequencies)))
        self.assertLess(error, 1e-12)
        self.assertTrue(np.isfinite(spectrum).all())
        self.assertAlmostEqual(sum(r['powers']['broad_rms'] for r in rows) / len(rows), 0.005, places=4)
        self.assertTrue(all(r['powers']['band_0_500'] > 0.004 for r in rows))


if __name__ == '__main__':
    unittest.main()
