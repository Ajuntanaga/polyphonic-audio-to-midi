import unittest
import numpy as np
from tools.harmonic_cell_unmix import recover


class HarmonicCellUnmixTest(unittest.TestCase):
    def test_known_weak_partial_and_negative_image(self):
        # Independent finite weighted lag sum, not response_matrix output.
        rate = 96000
        decay = np.exp(-1/(.040*rate))
        cells = 164.813778 * np.arange(1, 7)
        lag = np.arange(80000)
        weights = (1-decay)*decay**lag
        for cents in (0, -20):
            sources = cells * 2**(cents/1200)
            for phase in (0, np.pi/2):
                signal = .2*np.cos(2*np.pi*sources[0]*lag/rate)
                signal += .2*np.sqrt(2e-5)*np.cos(2*np.pi*sources[1]*lag/rate+phase)
                readings = np.array([np.sum(weights*signal*np.exp(2j*np.pi*f*lag/rate)) for f in cells])
                result = recover(cells, readings, sources, rate, decay)
                self.assertTrue(result['eligible'])
                powers = np.array(result['power'])
                self.assertAlmostEqual(powers[1]/powers[0], 2e-5, delta=1e-9)
                self.assertLess(max(powers[2:])/powers[0], 1e-14)

    def test_duplicate_sources_abstain(self):
        result = recover([100,200], [1j,2j], [100,100], 48000, .99)
        self.assertFalse(result['eligible'])

    def test_invalid_readings_rejected(self):
        with self.assertRaises(ValueError):
            recover([100], [complex('nan')], [100], 48000, .99)
