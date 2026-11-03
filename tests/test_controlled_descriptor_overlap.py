import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.controlled_descriptor_overlap import (
    controlled_mixtures, read_float_wave, write_float_wave, observations, compare_to_solo)


def row(sample, margin=2, **updates):
    result = dict(sample=str(sample), tick=str((sample + 1) // 64), note='36',
                  observed='1', fixed_context='0', complete_calibration='1',
                  posterior_observation_available='1', playable='3',
                  reserved_coasting='0', reserved_extras='0', phase_valid='0',
                  lane_terms=','.join(['0:0:0:0:0:0:0'] * 8),
                  posterior_detuning_valid_mask='0',
                  posterior_detuning_log_likelihood=','.join(['0'] * 8),
                  assignment_cents='0', learned_cents=','.join(['0'] * 8),
                  posterior_log_likelihood=f'{margin},0,0,0,0,0,0,0')
    result.update(updates)
    return result


def measured(rows, **updates):
    args = dict(note=36, lane=0, competitor=1, start=0, end=4096,
                sample_count=4096, sample_rate=10240, stride=1024)
    args.update(updates)
    return observations(rows, **args)


class ControlledOverlapTests(unittest.TestCase):
    def test_mixtures_share_target_gain_and_onset_without_clipping(self):
        target = np.array([0.8, -0.8, 0.8, -0.8])
        other = np.array([0.8, 0.8, -0.8, -0.8])
        cases = controlled_mixtures(target, {'other': other}, prefix=3, suffix=2)
        gains = {case['metadata']['common_gain'] for case in cases.values()}
        self.assertEqual(len(gains), 1)
        gain = gains.pop()
        self.assertLess(gain, 1)  # The loudest mixture determines attenuation for solo too.
        self.assertEqual(len({case['metadata']['target_component_sha256'] for case in cases.values()}), 1)
        for name, case in cases.items():
            audio = case['audio']
            np.testing.assert_array_equal(audio[:3], 0)
            np.testing.assert_array_equal(audio[-2:], 0)
            self.assertLessEqual(float(np.max(np.abs(audio))), 0.951)
            delta = audio[3:7].astype(float) - cases['solo']['audio'][3:7]
            expected = case['metadata']['interferer_scale'] * other * gain
            np.testing.assert_allclose(delta, expected, atol=1e-7)
        ratio = np.sqrt(np.mean((cases['other_-12dB']['audio'][3:7] -
                                 cases['solo']['audio'][3:7]) ** 2)) / (0.8 * gain)
        self.assertAlmostEqual(20 * np.log10(ratio), -12, places=5)

    def test_silent_and_mismatched_sources_cannot_be_silently_scored(self):
        for target, other in [([0, 0], [1, 1]), ([1, 1], [0, 0]),
                              ([1, 1], [1]), ([1, np.nan], [1, 1])]:
            with self.assertRaises(ValueError):
                controlled_mixtures(target, {'other': other}, prefix=0, suffix=0)

    def test_float_wave_roundtrip_preserves_samples_and_clock(self):
        samples = np.array([0, -0.125, 0.4, 0.95], dtype='<f4')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'case.wav'
            write_float_wave(path, 96000, samples)
            rate, restored = read_float_wave(path)
            self.assertEqual(rate, 96000)
            self.assertEqual(restored.tobytes(), samples.tobytes())
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                read_float_wave(path)

    def test_missing_and_reserved_observations_are_separate_from_zero(self):
        data = measured([row(1023, 0), row(2047, reserved_extras='2'),
                         row(4095, posterior_observation_available='0')])
        self.assertEqual(data['coverage'], dict(available=1, reserved_or_infeasible_pair=1,
                                               likelihood_unavailable=1, target_grid_frames=4,
                                               missing_target_row=1))
        self.assertEqual(data['observations'][1023]['margins']['descriptor'], 0)

    def test_pairing_uses_same_time_and_reports_missing_support(self):
        solo = measured([row(1023, 2), row(2047, -3), row(4095, 4)])
        mix = measured([row(1023, -2), row(3071, 6), row(4095, -1)])
        result = compare_to_solo(solo, mix)
        self.assertEqual((result['common_frames'], result['solo_available_only'],
                          result['mixed_available_only']), (2, 1, 1))
        attack = result['by_age']['attack_0_100ms']['terms']['descriptor']
        self.assertEqual(attack['mean_change'], -4)
        self.assertEqual(attack['positive_to_negative'], 1)
        self.assertEqual(attack['negative_change_percentage_points'], 100)
        self.assertEqual(result['by_age']['sustain_350ms_plus']['paired_frames'], 1)

    def test_bad_clock_duplicates_and_changed_target_geometry_are_refused(self):
        for rows in ([row(1023), row(1023)], [row(1000)], [row(1023, tick='2')],
                     [row(2047), row(1023)]):
            with self.assertRaises(ValueError):
                measured(rows)
        with self.assertRaisesRegex(ValueError, 'geometry'):
            compare_to_solo(measured([row(1023)]), measured([row(1023)], sample_rate=20480))

    def test_coasting_or_fixed_context_is_not_a_current_measurement(self):
        data = measured([row(1023, observed='0'), row(2047, fixed_context='1'),
                         row(3071, playable='1')])
        self.assertEqual(data['coverage']['not_current_observation'], 2)
        self.assertEqual(data['coverage']['reserved_or_infeasible_pair'], 1)
        self.assertEqual(data['observations'], {})
        self.assertEqual(compare_to_solo(data, data)['common_frames'], 0)


if __name__ == '__main__':
    unittest.main()
