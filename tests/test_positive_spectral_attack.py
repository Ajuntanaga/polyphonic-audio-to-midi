import math
import unittest

from tools.positive_spectral_attack import filterbank, logarithmic_bands, positive_flux, pick_events


def rows(values):
    return [{'feature': value, 'available_sample': (i + 1) * 480,
             'padded_samples': 0} for i, value in enumerate(values)]


class BandContracts(unittest.TestCase):
    def test_filters_have_peak_one_nonnegative_and_unique_centres(self):
        bank = filterbank(96000, 4096)
        centres = []
        for start, weights in bank:
            self.assertEqual(max(weights), 1)
            self.assertGreaterEqual(min(weights), 0)
            self.assertLessEqual(start + len(weights), 2048)
            centres.append(start + weights.index(1))
        self.assertEqual(centres, sorted(set(centres)))

    def test_silence_and_known_triangle(self):
        bank = [(0, [0, .5, 1, .5])]
        self.assertEqual(logarithmic_bands([0] * 4, bank), [0])
        self.assertAlmostEqual(logarithmic_bands([1] * 4, bank)[0], math.log10(3))

    def test_invalid_magnitude_and_geometry(self):
        for data in ([], [-1], [math.nan], [math.inf]):
            with self.assertRaises(ValueError):
                logarithmic_bands(data, [(0, [1])])
        with self.assertRaises(ValueError):
            logarithmic_bands([1], [(1, [1])])
        with self.assertRaises(ValueError):
            filterbank(96000, 4095)


class FluxContracts(unittest.TestCase):
    def test_unchanged_and_decreasing_bands_do_not_trigger(self):
        self.assertEqual(positive_flux([1, 2, 3], [1, 2, 3]), 0)
        self.assertEqual(positive_flux([.5, 1, 2], [1, 2, 3]), 0)

    def test_one_band_motion_is_suppressed(self):
        self.assertEqual(positive_flux([0, 0, 4, 0], [0, 4, 0, 0]), 0)

    def test_positive_growth_is_kept_including_late_bloom_risk(self):
        self.assertEqual(positive_flux([0, 5, 0], [0, 2, 0]), 3)
        self.assertEqual(positive_flux([2, 0, 3], [0, 0, 0]), 5)

    def test_edges_do_not_wrap(self):
        self.assertEqual(positive_flux([4, 0, 0], [0, 0, 4]), 4)

    def test_invalid_band_vectors(self):
        for current, previous in (([], []), ([1], [1, 2]), ([math.nan], [0]), ([-1], [0])):
            with self.assertRaises(ValueError):
                positive_flux(current, previous)


class ClockContracts(unittest.TestCase):
    def test_silence_cannot_trigger(self):
        self.assertEqual(pick_events(rows([0] * 50)), [])

    def test_future_cannot_change_events(self):
        prefix = rows([0, 4, 0, 0, 0, 0, 0, 0, 4, 0])
        a = pick_events(prefix)
        b = pick_events(prefix + rows([0] * 10 + [100])[10:])
        self.assertEqual(a, [e for e in b if e['available_sample'] <= 4800])

    def test_clock_is_hop_end_and_refractory_strict(self):
        events = pick_events(rows([3, 0, 0, 0, 0, 0, 3, 3]),
                             threshold=1, max_history=0, mean_history=20)
        self.assertEqual([e['available_sample'] for e in events], [480, 3840])
        self.assertTrue(all(e['nominal_sample'] == e['available_sample'] for e in events))


if __name__ == '__main__':
    unittest.main()
