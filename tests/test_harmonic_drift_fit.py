import json
import unittest

import numpy as np
from scipy.signal import chirp

from tools.harmonic_drift_fit import _fit_model, fit_window


def sources():
    return [
        {"string": 0, "fret": 8, "cents": -42.375, "partial_cents": [0, 4.582, 0],
         "valid_mask": 3, "profile": [0.966277, 0.033357, 0.000366]},
        {"string": 1, "fret": 4, "cents": -23.227, "partial_cents": [0, 1.082, 4.672],
         "valid_mask": 7, "profile": [0.739372, 0.255715, 0.004669]},
        {"string": 2, "fret": 0, "cents": -12.672, "partial_cents": [0, 6.695, 7.035],
         "valid_mask": 7, "profile": [0.263070, 0.645100, 0.090330]},
    ]


def signal(times, center, templates, starts, ends, growth):
    values = np.zeros((3, len(times)), dtype=complex)
    for i, source in enumerate(templates):
        for h in range(3):
            first = (h + 1) * center * (2 ** ((starts[i] + source["partial_cents"][h]) / 1200) - 1)
            last = (h + 1) * center * (2 ** ((ends[i] + source["partial_cents"][h]) / 1200) - 1)
            phase = 17 * (source["string"] + 1) * (h + 1)
            tone = chirp(times, f0=first, t1=times[-1], f1=last, phi=phase)
            tone = tone + 1j * chirp(times, f0=first, t1=times[-1], f1=last, phi=phase - 90)
            values[h] += np.sqrt(source["profile"][h]) * np.exp(growth[i] * times) * tone
    return values


class HarmonicDriftFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.times = np.arange(301) * 0.01
        cls.center = 440 * 2 ** ((40 - 69) / 12)
        cls.single = sources()[2:]
        cls.single_signal = signal(cls.times, cls.center, cls.single, [-20], [-20], [-0.35])
        cls.single_fit = fit_window(cls.times, cls.single_signal, cls.center, 40, cls.single, 200, 96000)

    def test_gain_evolution_predicts_newer_audio(self):
        model = next(m for m in self.single_fit["models"] if m["fit_family"] == "gain_drift")
        control = next(m for m in self.single_fit["models"] if m["fit_family"] == "static")
        self.assertLess(model["test_prediction_loss"], 1e-9)
        self.assertGreater(control["test_prediction_loss"], 0.01)
        self.assertAlmostEqual(model["members"][0]["growth_per_second"], -0.35, places=5)
        json.dumps(self.single_fit, allow_nan=False)

    def test_future_values_cannot_change_fitted_evolution(self):
        changed = self.single_signal.copy()
        changed[:, 200:] *= 2 * np.exp(0.8j)
        actual = fit_window(self.times, changed, self.center, 40, self.single, 200, 96000)
        for before, after in zip(self.single_fit["models"], actual["models"]):
            if before["fit_family"] == "static":
                self.assertEqual(before["members"][0]["cents"], after["members"][0]["cents"])
            else:
                for key in ("cents_at_start", "cents_at_end", "growth_per_second"):
                    self.assertEqual(before["members"][0][key], after["members"][0][key])

    def test_a_moving_pair_does_not_need_a_false_third_string(self):
        templates = sources()
        values = signal(self.times, self.center, [templates[0], templates[2]],
                        [-31, -13], [-27, -17], [-0.4, 0.1])
        result = fit_window(self.times, values, self.center, 40, templates, 200, 96000)
        pair = next(m for m in result["models"] if m["mask"] == 5 and m["fit_family"] == "pitch_and_gain")
        self.assertLess(pair["test_prediction_loss"], 1e-7)
        self.assertFalse(any(m["mask"] == 7 and m["independent_cross_band_support"] for m in result["models"]))

    def test_four_independent_pitch_drifts_can_be_estimated(self):
        templates = [{"string": i, "fret": 20 - 4 * i, "cents": -35 + i * 18,
                      "valid_mask": 7, "partial_cents": [0, i * 3, i * 5],
                      "profile": [0.5, 0.35, 0.15]} for i in range(4)]
        center = 440 * 2 ** ((52 - 69) / 12)
        first, last = [-28, -9, 12, 31], [-25, -12, 15, 28]
        values = signal(self.times, center, templates, first, last, [0, 0, 0, 0])
        control = {"mask": 15, "members": [{"cents": (a + b) / 2} for a, b in zip(first, last)]}
        fitted = _fit_model(self.times, values, center, templates, 200, 7, control, "pitch_drift")
        self.assertLess(fitted["test_prediction_loss"], 1e-8)
        np.testing.assert_allclose([m["cents_at_start"] for m in fitted["members"]], first, atol=1e-4)
        np.testing.assert_allclose([m["cents_at_end"] for m in fitted["members"]], last, atol=1e-4)


if __name__ == "__main__":
    unittest.main()
