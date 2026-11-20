import unittest
from unittest.mock import patch
from pathlib import Path
from tools.portable_octave_parent_measurement import run, validate_inventory, take_measurement_bounds
import numpy as np
from tools.octave_parent_measurement import production_harmonics, six_frequency_energy, held_pass_errors


class ParentMeasurementTests(unittest.TestCase):
    def test_local_execution_refused_before_io(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS':'false'}):
            with self.assertRaisesRegex(RuntimeError, 'GitHub Actions'):
                run(*([Path('/nonexistent')] * 5))

    def test_frozen_inventory_rejects_missing_take(self):
        with self.assertRaisesRegex(ValueError, '96 frozen'):
            validate_inventory({'takes':[]})

    def test_short_label_remains_unavailable_without_window_shift(self):
        self.assertIsNone(take_measurement_bounds(96000, 123600, 96000))
        self.assertEqual(take_measurement_bounds(96000, 142080, 96000), (54720, 70080))

    def test_enabled_bins(self):
        self.assertEqual([production_harmonics(n) for n in (44,48,60,62,69)], [6,6,4,4,4])

    def test_projection_amplitude_squared(self):
        rate = 48000
        t = np.arange(rate) / rate
        signal = .4*np.cos(2*np.pi*440*t) + .1*np.sin(2*np.pi*880*t)
        energy = six_frequency_energy(signal, rate, 69)
        np.testing.assert_allclose(energy[:2], [.16,.01], rtol=1e-5)
        self.assertLess(max(energy[2:]), 1e-12)

    def test_whole_pass_excluded_and_unavailable_retained(self):
        rows = [dict(take_id=str(i), note=60, lane=1, held_pass=p,
                     runtime_energy=e) for i,p,e in
                [(0,1,[1,1,1,1]), (1,1,[1,100,100,100]), (2,2,[1,10,10,10])]]
        result = held_pass_errors(rows, 'runtime_energy')
        self.assertEqual([r['training_count'] for r in result], [1,1,2])
        np.testing.assert_allclose(result[0]['error_db'], [-10]*3)
        self.assertFalse(held_pass_errors(rows[:2], 'runtime_energy')[0]['available'])
        rows[0]['runtime_energy'] = [1,1,1,1,0,0]
        self.assertEqual(held_pass_errors(rows, 'runtime_energy')[0]['reason'], 'invalid_observation')

if __name__ == '__main__':
    unittest.main()
