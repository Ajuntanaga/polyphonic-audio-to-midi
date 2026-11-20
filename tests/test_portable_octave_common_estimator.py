import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import portable_octave_common_estimator as m


def row(sample, h1=100, h2=10):
    return dict(sample=str(sample), note='60', corrected_harmonic_energy_1=h1,
        corrected_harmonic_energy_2=h2, phase_valid=1, independent_phase_valid=0,
        active=0, evidence=0, selection=2, assigned_mask=0,
        phase_cents=0, independent_phase_cents=0)


class CommonEstimatorTests(unittest.TestCase):
    def test_local_guard_before_io(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS':'false'}):
            with self.assertRaisesRegex(RuntimeError, 'GitHub Actions'):
                m.run(*([Path('/nonexistent')] * 7))

    def test_pcm16_reader_exact_native_scale(self):
        import wave, struct
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.wav'
            with wave.open(str(path),'wb') as out:
                out.setparams((1,2,96000,0,'NONE','not compressed'))
                out.writeframes(struct.pack('<5h',-32768,-1,0,1,32767))
            rate,values=m.read_pcm16_wave(path)
            self.assertEqual(rate,96000)
            np.testing.assert_array_equal(values,np.array([-1,-1/32768,0,1/32768,32767/32768],dtype=np.float32))
            m.write_float_wave(path,96000,values)
            with self.assertRaises(wave.Error): m.read_pcm16_wave(path)

    def test_retained_parent_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'report.json'
            current={k:k for k in ('protocol','binary_sha256','inventory_sha256','sources_sha256','plan_sha256')}
            previous=dict(current,measurements=[dict(kind='parent_only') for _ in range(21)])
            path.write_text(json.dumps(previous))
            with self.assertRaisesRegex(ValueError,'hash mismatch'): m.retained_parents(path,current)
            with patch.object(m,'PARENT_REPORT_SHA256',m.digest(path)):
                self.assertEqual(len(m.retained_parents(path,current)),21)
                with self.assertRaisesRegex(ValueError,'provenance mismatch'):
                    m.retained_parents(path,dict(current,binary_sha256='changed'))

    def test_frozen_metadata_selection(self):
        root=Path(__file__).resolve().parents[1]
        inventory=json.loads((root/'docs/recovery/octave-parent-inventory-20261120.json').read_text())
        plan=json.loads((root/'docs/recovery/octave-common-estimator-plan-20261120.json').read_text())
        self.assertEqual(len(m.select_takes(inventory,plan)),21)
        plan['cases'].pop()
        with self.assertRaises(ValueError): m.select_takes(inventory,plan)

    def test_join_keeps_rejected_cells_and_zero_coverage(self):
        rows=m.join_rows([row(63),row(127,0)], [row(63,1),row(127,1)],0,128)
        self.assertEqual(rows[0]['parent_h2_over_h1_db'],-10)
        self.assertEqual(rows[0]['upper_h1_over_parent_h1_db'],-20)
        summary=m.summarize(rows)
        self.assertEqual(summary['ticks'],2)
        self.assertEqual(summary['upper']['active'],0)
        self.assertEqual(summary['energies']['parent_h1']['median'],50)
        self.assertFalse(summary['channels'][m.CHANNELS[0]]['complete'])
        self.assertEqual(summary['channels'][m.CHANNELS[0]]['unavailable_ticks'],1)
        with self.assertRaises(ValueError): m.join_rows([row(63)],[row(127)],0,64)
        with self.assertRaises(ValueError): m.join_rows([row(63,float('nan'))],[row(63)],0,64)

    def test_exact_cadence_and_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trace.tsv'
            p.write_text('sample\tnote\n63\t72\n127\t72\n')
            self.assertEqual(len(m.checked_rows(p,72,0,128)),2)
            with self.assertRaises(ValueError): m.checked_rows(p,60,0,128)
            p.write_text('sample\tnote\n63\t72\n63\t72\n')
            with self.assertRaises(ValueError): m.checked_rows(p,72,0,128)

    def test_whole_pass_exclusion_and_unavailable_retention(self):
        items=[]
        for name,p,value in [('a',1,1),('b',1,100),('c',2,10),('d',3,None)]:
            items.append(dict(id=name,kind='parent_only',parent=48,lane=1,held_pass=p,
                summary={'channels':{k:dict(complete=value is not None,distribution={'median':value}) for k in m.CHANNELS}}))
        items.append(dict(id='control',kind='annotated_octave',parent=48,lane=1,summary=items[0]['summary']))
        result=m.comparisons(items)
        first=result['held_pass'][0]['channels'][m.CHANNELS[0]]
        self.assertEqual(first['training_ids'],['c'])
        self.assertEqual(first['unavailable_training_ids'],['d'])
        self.assertEqual(first['difference_db'],-9)
        self.assertEqual(len(result['held_pass']),4)
        self.assertEqual(result['controls'][0]['channels'][m.CHANNELS[0]]['training_count'],3)

    def test_annotation_clipping_preserves_overlapping_chord(self):
        labels=[dict(start_sample=0,end_sample=110,midi_note=44),dict(start_sample=105,end_sample=140,midi_note=56),dict(start_sample=140,end_sample=150,midi_note=72)]
        self.assertEqual(m.clip_labels(labels,100,130),[dict(start_sample=0,end_sample=10,midi_note=44),dict(start_sample=5,end_sample=30,midi_note=56)])
        self.assertEqual(labels[0]['start_sample'],0)

if __name__=='__main__': unittest.main()
