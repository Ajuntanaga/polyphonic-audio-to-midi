import unittest

from tools.string_likelihood_decomposition import pair_margins


def observation():
    return dict(complete_calibration='1', posterior_observation_available='1',
                playable='3', reserved_coasting='0', reserved_extras='0',
                lane_terms='0:0:-256:0:0:0:0,0:0:256:0:0:0:0,' +
                           ','.join(['0:0:0:0:0:0:0'] * 6),
                posterior_detuning_valid_mask='3',
                posterior_detuning_log_likelihood='-2,2,0,0,0,0,0,0',
                assignment_cents='0', phase_valid='1', learned_cents='0,8,0,0,0,0,0,0',
                posterior_log_likelihood='-9,7,0,0,0,0,0,0')


class LikelihoodDecompositionTests(unittest.TestCase):
    def test_known_components_recover_descriptor_and_margin_direction(self):
        # Profile +3/-3, cents 0/-2, detuning -2/+2, descriptor -10/+10.
        row = observation()
        self.assertEqual(pair_margins(row, 0, 1),
                         dict(profile=6, cents=2, detuning=-4, descriptor=-20, total=-16))
        self.assertEqual(pair_margins(row, 1, 0),
                         dict(profile=-6, cents=-2, detuning=4, descriptor=20, total=16))

    def test_invalid_phase_contributes_zero_and_cents_penalty_caps(self):
        row = observation()
        row['phase_valid'] = '0'
        self.assertEqual(pair_margins(row, 0, 1)['cents'], 0)
        row.update(phase_valid='1', learned_cents='0,100,0,0,0,0,0,0')
        self.assertEqual(pair_margins(row, 0, 1)['cents'], 16)

    def test_unavailable_detuning_differs_from_valid_zero(self):
        row = observation()
        row['posterior_detuning_log_likelihood'] = '0,0,0,0,0,0,0,0'
        self.assertEqual(pair_margins(row, 0, 1)['detuning'], 0)
        row['posterior_detuning_valid_mask'] = '0'
        self.assertEqual(pair_margins(row, 0, 1)['detuning'], 0)
        row['posterior_detuning_log_likelihood'] = '-2,2,0,0,0,0,0,0'
        with self.assertRaisesRegex(ValueError, 'unavailable detuning'):
            pair_margins(row, 0, 1)

    def test_reserved_unplayable_and_incomplete_evidence_are_refused(self):
        for field, value in [('reserved_coasting', '2'), ('reserved_extras', '1'),
                             ('playable', '1'), ('complete_calibration', '0'),
                             ('posterior_observation_available', '0')]:
            row = observation(); row[field] = value
            with self.assertRaises(ValueError):
                pair_margins(row, 0, 1)

    def test_invalid_or_uncentered_detuning_is_refused(self):
        for field, value in [('posterior_detuning_valid_mask', '4'),
                             ('posterior_detuning_log_likelihood', '1,1,0,0,0,0,0,0'),
                             ('posterior_detuning_log_likelihood', 'nan,0,0,0,0,0,0,0'),
                             ('assignment_cents', 'nan')]:
            row = observation(); row[field] = value
            with self.assertRaises(ValueError):
                pair_margins(row, 0, 1)


if __name__ == '__main__':
    unittest.main()
