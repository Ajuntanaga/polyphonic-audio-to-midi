import unittest
from tools.runtime_profile_generalization import evaluate

class GeneralizationTest(unittest.TestCase):
    def rows(self):
        return [dict(clip=f'{lane}-{note}',string=lane,midi_note=note,pass_id=note,**{'pass':note},eligible=True,measurement_source='runtime',shares=([.8,.1,.04,.03,.02,.01] if lane==0 else [.1,.8,.04,.03,.02,.01])) for lane in (0,1) for note in (52,55)]
    def test_pitch_split_and_scale_invariance(self):
        rows=self.rows();rows[0]['shares']=[x*10 for x in rows[0]['shares']]
        result=evaluate(rows,holdout='midi_note',lanes=[0,1])
        self.assertEqual(result['correct'],4)
        for fold in result['folds']:
            self.assertTrue(all(int(c.split('-')[1])!=fold['held'] for c in fold['training_clips']))
    def test_single_pitch_cannot_validate_pitch_generalization(self):
        result=evaluate([r for r in self.rows() if r['midi_note']==52],holdout='midi_note',lanes=[0,1])
        self.assertEqual((result['total'],result['correct'],result['abstained']),(2,0,2))
    def test_ineligible_retained(self):
        rows=self.rows();rows[0]['eligible']=False
        result=evaluate(rows,holdout='pass',lanes=[0,1])
        self.assertEqual(result['total'],4)
        self.assertGreaterEqual(result['abstained'],1)
    def test_reject_wrong_measurement_or_duplicate(self):
        rows=self.rows();rows[0]['measurement_source']='spectral'
        with self.assertRaises(ValueError):evaluate(rows,holdout='pass',lanes=[0,1])
        rows=self.rows()
        with self.assertRaises(ValueError):evaluate(rows+[rows[0]],holdout='pass',lanes=[0,1])
