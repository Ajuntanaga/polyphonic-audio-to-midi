"""Checks of the narrow-band level measurement used by the audio-level read of label ends (pure numpy, synthetic signals only)."""
import math
import unittest

import numpy as np

from tools import audio_release_levels as lv

RATE = lv.SOURCE_RATE


def tone(midi, seconds, amplitude=0.5, harmonic=1, phase=0.3):
    t = np.arange(int(seconds * RATE)) / RATE
    return amplitude * np.sin(2 * np.pi * harmonic * lv.fundamental(midi) * t + phase)


class LevelMeasurement(unittest.TestCase):
    def test_conventions(self):
        self.assertEqual(lv.ms_samples(80), 7680)
        self.assertAlmostEqual(lv.fundamental(69), 440.0)
        self.assertAlmostEqual(lv.fundamental(57), 220.0)
        self.assertEqual(lv.harmonic_numbers(69), [1, 2, 3, 4])
        self.assertEqual(lv.harmonic_numbers(40), [1, 2, 3, 4])
        self.assertEqual(lv.harmonic_numbers(84), [1])           # 2 * 1046.5 Hz is above 2 kHz
        self.assertEqual(lv.harmonic_numbers(78), [1, 2])        # 740 Hz, 1480 Hz; 3 * 740 is above 2 kHz
        self.assertEqual(lv.END_GRID, (-20, 30))
        self.assertEqual(lv.START_GRID, (-20, 20))
        self.assertEqual(lv.grid_index(lv.END_GRID, -20), 0)
        self.assertEqual(lv.grid_index(lv.END_GRID, 30), 50)
        self.assertIsNone(lv.grid_index(lv.END_GRID, 31))

    def test_sinusoid_amplitude(self):
        for midi in (45, 57, 69):
            x = tone(midi, 0.6, amplitude=0.5)
            levels = lv.window_levels(x, midi, 4000, 20, 960)
            self.assertTrue(np.isfinite(levels).all())
            self.assertTrue(np.all(np.abs(levels - 20 * math.log10(0.5)) < 0.3), (midi, levels.min(), levels.max()))

    def test_position_and_phase_do_not_matter(self):
        x = tone(60, 0.6, amplitude=0.25, phase=1.1)
        a = lv.window_levels(x, 60, 3000, 1, 1)[0]
        b = lv.window_levels(x, 60, 3000 + 137, 1, 1)[0]
        self.assertLess(abs(a - b), 0.25)

    def test_dc_offset_is_removed(self):
        x = tone(60, 0.5, amplitude=0.25)
        clean = lv.window_levels(x, 60, 5000, 5, 960)
        shifted = lv.window_levels(x + 0.3, 60, 5000, 5, 960)
        self.assertTrue(np.all(np.abs(clean - shifted) < 0.1))

    def test_harmonics_add_in_power(self):
        midi = 57
        x = sum(tone(midi, 0.5, amplitude=0.1, harmonic=k, phase=0.2 * k) for k in (1, 2, 3, 4))
        level = lv.window_levels(x, midi, 6000, 1, 1)[0]
        self.assertAlmostEqual(level, 20 * math.log10(0.1 * 2.0), delta=0.3)       # sqrt(4) * 0.1

    def test_a_distant_pitch_is_far_below(self):
        x = tone(76, 0.5, amplitude=0.5)
        own = lv.window_levels(x, 76, 6000, 1, 1)[0]
        other = lv.window_levels(x, 69, 6000, 1, 1)[0]
        self.assertGreater(own - other, 30.0)

    def test_a_step_down_is_measured_before_and_after(self):
        midi, edge = 62, 24000
        x = tone(midi, 0.6)
        x[edge:] *= 0.1                                            # -20 dB at 250 ms
        before = lv.window_levels(x, midi, edge - 7680, 1, 1)[0]
        after = lv.window_levels(x, midi, edge, 1, 1)[0]
        straddling = lv.window_levels(x, midi, edge - 3840, 1, 1)[0]
        self.assertAlmostEqual(after - before, -20.0, delta=0.3)
        self.assertTrue(after < straddling < before)

    def test_windows_that_do_not_fit_are_nan(self):
        x = tone(60, 0.3)
        out = lv.window_levels(x, 60, -960, 4, 960)               # the first starts before the signal
        self.assertTrue(np.isnan(out[0]) and np.isfinite(out[1]))
        tail = lv.window_levels(x, 60, len(x) - 7680 - 960, 3, 960)   # the last two run past the end
        self.assertTrue(np.isfinite(tail[0]) and np.isfinite(tail[1]) and np.isnan(tail[2]))
        self.assertTrue(np.isnan(lv.window_levels(x, 60, len(x), 2, 960)).all())

    def test_silence_hits_the_floor(self):
        out = lv.window_levels(np.zeros(20000), 60, 0, 2, 960)
        self.assertTrue(np.all(out <= 20 * math.log10(lv.FLOOR) + 1e-6))

    def test_curves_use_the_grids(self):
        midi, end = 62, 30000
        x = tone(midi, 1.0)
        curve = lv.end_curve(x, midi, end)
        self.assertEqual(len(curve), 51)
        i = lv.grid_index(lv.END_GRID, -8)
        direct = lv.window_levels(x, midi, end - 8 * 960, 1, 1)[0]
        self.assertAlmostEqual(curve[i], direct, places=9)
        starts = lv.start_curve(x, midi, 40000)
        self.assertEqual(len(starts), 41)
        self.assertAlmostEqual(starts[lv.grid_index(lv.START_GRID, 0)], lv.window_levels(x, midi, 40000, 1, 1)[0], places=9)
        early = lv.end_curve(x, midi, 5000)                       # grid starts before the signal: early entries are NaN
        self.assertTrue(np.isnan(early[0]) and np.isfinite(early[-1]))


if __name__ == '__main__':
    unittest.main()
