import unittest
from tools.portable_runtime_profile_generalization import profile, validate_manifest


class RuntimeProfileProtocolTests(unittest.TestCase):
    def rows(self):
        return [dict(sample=str(s), independent_phase_valid='1', independent_phase_cents='0',
            **{f'corrected_harmonic_energy_{h}':str(h) for h in range(1,7)}) for s in (0,80)]

    def test_fixed_halves_and_phase_abstention(self):
        rows = self.rows()
        result = profile(rows,0,1000)
        self.assertTrue(result['eligible'])
        self.assertAlmostEqual(sum(result['shares']),1)
        rows[1]['independent_phase_valid']='0'
        self.assertFalse(profile(rows,0,1000)['eligible'])

    def test_missing_half_and_out_of_window(self):
        rows = self.rows()
        rows[1]['sample']='160'
        self.assertFalse(profile(rows,0,1000)['eligible'])

    def test_wrong_pitch_and_path_rejected(self):
        clip=dict(clip='../outside.wav',string=0,pass_=1,midi_note=52,labeled_begin=0,labeled_end=200)
        clip['pass']=clip.pop('pass_')
        with self.assertRaises(ValueError): validate_manifest({'clips':[clip]})
        clip['clip']='take.wav';clip['midi_note']=57
        with self.assertRaises(ValueError): validate_manifest({'clips':[clip]})

    def test_nonfinite_phase_abstains(self):
        rows=self.rows();rows[0]['independent_phase_cents']='nan'
        self.assertFalse(profile(rows,0,1000)['eligible'])


if __name__=='__main__': unittest.main()
