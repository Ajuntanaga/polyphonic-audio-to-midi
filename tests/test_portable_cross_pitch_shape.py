import copy
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from tools.portable_cross_pitch_shape import evaluate_window, run, read_input_wave


class RunnerContracts(unittest.TestCase):
    def setUp(self):
        self.rate = 8000
        t = np.arange(1280) / self.rate
        self.samples = np.cos(2*np.pi*165*t) + .4*np.cos(2*np.pi*185*t)
        self.window = dict(id='synthetic', begin=0, end=1280,
                           sample_rate_hz=self.rate, wave_sha256='0'*64,
                           frequency_sets=[dict(input_role='annotation_oracle',
                               fundamentals_hz=[165, 185], provenance=dict(
                                   source='labels.json', sha256='1'*64, sample=0))])

    def test_roles_are_separate_and_omitted_competitor_is_visible(self):
        candidate = copy.deepcopy(self.window['frequency_sets'][0])
        candidate.update(input_role='detector_candidates', fundamentals_hz=[165])
        self.window['frequency_sets'].append(candidate)
        oracle, detector = evaluate_window(self.samples, self.rate, self.window)['fits']
        self.assertLess(oracle['validation_residual_ratio'], 1e-20)
        self.assertGreater(detector['validation_residual_ratio'], .01)
        self.assertFalse(detector['policy_admission'])

    def test_future_detector_frequencies_rejected(self):
        spec = self.window['frequency_sets'][0]
        spec['input_role'] = 'detector_candidates'
        spec['provenance']['sample'] = 1
        with self.assertRaisesRegex(ValueError, 'precede'):
            evaluate_window(self.samples, self.rate, self.window)

    def test_clock_and_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError, 'rate mismatch'):
            evaluate_window(self.samples, 16000, self.window)
        self.window['end'] += 1
        with self.assertRaisesRegex(ValueError, 'bounded'):
            evaluate_window(self.samples, self.rate, self.window)

    def test_shared_harmonics_abstain(self):
        self.window['frequency_sets'][0]['fundamentals_hz'] = [165, 330]
        result = evaluate_window(self.samples, self.rate, self.window)['fits'][0]
        self.assertEqual(result['abstention'], 'unidentifiable_coefficients')

    def test_pcm16_and_float_inputs_preserve_amplitude(self):
        from scipy.io import wavfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.wav'
            pcm = np.array([-32768, -123, 0, 123, 32767], dtype=np.int16)
            wavfile.write(path, self.rate, pcm)
            rate, decoded = read_input_wave(path)
            self.assertEqual(rate, self.rate)
            np.testing.assert_array_equal(decoded, pcm.astype(float) / 32768)
            floating = (pcm.astype(float) / 32768).astype(np.float32)
            wavfile.write(path, self.rate, floating)
            np.testing.assert_array_equal(read_input_wave(path)[1], floating)
            wavfile.write(path, self.rate, pcm.astype(np.int32))
            with self.assertRaisesRegex(ValueError, 'PCM16 or float32'):
                read_input_wave(path)

    def test_local_recorded_entry_rejected_before_read(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaisesRegex(RuntimeError, 'GitHub Actions'):
                run({}, '/does-not-exist')


if __name__ == '__main__':
    unittest.main()
