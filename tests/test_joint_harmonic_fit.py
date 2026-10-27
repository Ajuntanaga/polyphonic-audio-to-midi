import copy
import unittest

import numpy as np

from tools.joint_harmonic_fit import _frequencies, fit_mask, fit_window


def templates():
    return [
        {"string": 0, "fret": 8, "cents": -42.375, "partial_cents": [0, 4.582, 0],
         "valid_mask": 3, "profile": [0.966277, 0.033357, 0.000366]},
        {"string": 1, "fret": 4, "cents": -23.227, "partial_cents": [0, 1.082, 4.672],
         "valid_mask": 7, "profile": [0.739372, 0.255715, 0.004669]},
        {"string": 2, "fret": 0, "cents": -12.672, "partial_cents": [0, 6.695, 7.035],
         "valid_mask": 7, "profile": [0.263070, 0.645100, 0.090330]},
    ]


def synthesize(times, center, sources, cents, gains=None):
    frequency = _frequencies(center, cents, sources)
    signal = np.zeros((3, len(times)), dtype=complex)
    if gains is None:
        gains = np.ones(len(sources))
    for h in range(3):
        for i, source in enumerate(sources):
            # Physical harmonic energy exists even when its calibration offset
            # is not known. The synthesizer knows its actual offset separately.
            if source["profile"][h] > 0:
                amplitude = gains[i] * np.sqrt(source["profile"][h])
                phase = 0.41 * (source["string"] + 1) * (h + 1)
                signal[h] += amplitude * np.exp(1j * (2 * np.pi * frequency[h, i] * times + phase))
    return signal


class JointHarmonicFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.times = np.arange(301) * 0.01
        cls.center = 440 * 2 ** ((40 - 69) / 12)
        cls.sources = templates()
        cls.signal = synthesize(cls.times, cls.center, cls.sources, [-31, -19, -13])
        cls.fit = fit_window(cls.times, cls.signal, cls.center, 40, cls.sources, 200, 96000)

    def test_recovers_three_current_pitches_across_harmonics(self):
        model = next(m for m in self.fit["models"] if m["mask"] == 7)
        self.assertLess(model["test_refit_loss"], 1e-10)
        self.assertLess(model["test_prediction_loss"], 1e-9)
        np.testing.assert_allclose([s["cents"] for s in model["members"]], [-31, -19, -13], atol=1e-4)
        self.assertTrue(model["independent_cross_band_support"])

    def test_rejects_a_false_third_string_in_a_pair(self):
        signal = synthesize(self.times, self.center, [self.sources[0], self.sources[2]], [-31, -13])
        result = fit_window(self.times, signal, self.center, 40, self.sources, 200, 96000)
        pair = next(m for m in result["models"] if m["mask"] == 5)
        triple = next(m for m in result["models"] if m["mask"] == 7)
        self.assertLess(pair["test_refit_loss"], 1e-9)
        self.assertTrue(pair["independent_cross_band_support"])
        self.assertFalse(triple["independent_cross_band_support"])

    def test_frequencies_use_training_only(self):
        changed = self.signal.copy()
        changed[:, 200:] = synthesize(self.times[200:], self.center, self.sources, [12, 8, -2])
        actual = fit_mask(self.times, changed, self.center, self.sources, 200, 96000)
        control = next(m for m in self.fit["models"] if m["mask"] == 7)
        self.assertEqual([m["cents"] for m in actual["members"]], [m["cents"] for m in control["members"]])
        self.assertGreater(actual["test_prediction_loss"], 0.1)

    def test_gain_and_input_order_do_not_change_mask_evidence(self):
        actual = fit_window(self.times, self.signal * 1e-4, self.center, 40,
                            list(reversed(self.sources)), 200, 96000)
        for a, b in zip(self.fit["models"], actual["models"]):
            self.assertEqual(a["mask"], b["mask"])
            self.assertEqual(a["independent_cross_band_support"], b["independent_cross_band_support"])
            self.assertAlmostEqual(a["test_refit_loss"], b["test_refit_loss"], places=5)

    def test_ambiguous_duplicate_sources_do_not_establish_an_extra_string(self):
        sources = copy.deepcopy(self.sources[:2])
        for source in sources:
            source.update({"cents": -10, "partial_cents": [0, 0, 0],
                           "valid_mask": 7, "profile": [0.6, 0.3, 0.1]})
        signal = synthesize(self.times, self.center, sources[:1], [-10])
        result = fit_window(self.times, signal, self.center, 40, sources, 200, 96000)
        self.assertFalse(next(m for m in result["models"] if m["mask"] == 3)["independent_cross_band_support"])

    def test_four_sources_fit_and_fret_bounds_are_enforced(self):
        sources = []
        for i in range(4):
            sources.append({"string": i, "fret": 20 - 4 * i, "cents": -35 + i * 18,
                            "valid_mask": 7, "partial_cents": [0, i * 3, i * 5],
                            "profile": [0.5, 0.35, 0.15]})
        center = 440 * 2 ** ((52 - 69) / 12)
        signal = synthesize(self.times, center, sources, [-28, -9, 12, 31])
        result = fit_window(self.times, signal, center, 52, sources, 200, 96000)
        four = next(m for m in result["models"] if m["mask"] == 15)
        self.assertLess(four["test_refit_loss"], 1e-9)
        self.assertTrue(four["independent_cross_band_support"])
        sources[0]["fret"] = 25
        with self.assertRaises(ValueError):
            fit_window(self.times, signal, center, 52, sources, 200, 96000)

    def test_invalid_observation_times_and_sampling_range_are_rejected(self):
        times = self.times.copy()
        times[2] = times[1]
        with self.assertRaises(ValueError):
            fit_window(times, self.signal, self.center, 40, self.sources, 200, 96000)
        result = fit_window(self.times, self.signal, 1046.5, 40, self.sources[:1], 200, 96000)
        self.assertFalse(result["median_spacing_guard_passed"])
        self.assertFalse(result["models"][0]["independent_cross_band_support"])

    def test_unknown_detuning_does_not_mean_an_absent_physical_harmonic(self):
        changed = self.signal.copy()
        changed[2] += 1000 * np.exp(2j * np.pi * 1.7 * self.times)
        actual = fit_window(self.times, changed, self.center, 40, self.sources, 200, 96000)
        self.assertEqual(actual["comparison_harmonic_mask"], 3)
        for a, b in zip(self.fit["models"], actual["models"]):
            self.assertEqual(a["mask"], b["mask"])
            self.assertEqual(a["test_refit_loss"], b["test_refit_loss"])
            self.assertEqual(a["members"], b["members"])

    def test_large_observation_gap_cannot_qualify_an_extra_string(self):
        times = self.times[(self.times < 0.8) | (self.times > 1.4)]
        signal = synthesize(times, self.center, self.sources, [-31, -19, -13])
        result = fit_window(times, signal, self.center, 40, self.sources,
                            len(times) * 2 // 3, 96000)
        self.assertTrue(result["median_spacing_guard_passed"])
        self.assertFalse(result["conservative_spacing_guard_passed"])
        self.assertTrue(next(m for m in result["models"] if m["mask"] == 7)["cross_band_residual_support"])
        self.assertFalse(any(m["independent_cross_band_support"] for m in result["models"]))


if __name__ == "__main__":
    unittest.main()
