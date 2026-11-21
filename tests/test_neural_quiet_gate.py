"""Synthetic gate report checks; no model, audio or native execution."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_neural_quiet_gate as runner


class NeuralQuietGateTests(unittest.TestCase):
    def test_generated_identity_ignores_only_scheduling(self):
        a=[dict(frame=1,note=48,on=1,source_end=640,ready_ns=7000000)]
        b=[dict(a[0],ready_ns=8000000)]
        self.assertTrue(runner.generated_identity(a,b)['pass_'])
        for key in ('frame','note','on','source_end'):
            c=[dict(b[0])];c[0][key]+=1
            result=runner.generated_identity(a,c)
            self.assertFalse(result['pass_']);self.assertEqual(result['first_difference_index'],0)
        self.assertFalse(runner.generated_identity(a,[])['pass_'])

    def test_gate_mechanism_and_closed_owner_release(self):
        summary=dict(model_calls=2,gate_closed_frames=2,gate_forced_releases=1,
                     gate_enabled=True,gate_threshold_db=-60.0)
        events=[dict(frame=0,note=48,on=1,source_end=8320),
                dict(frame=2,note=48,on=0,source_end=10880)]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gate.tsv'
            path.write_text('source_end\tframe\tpower\tenabled\topen\n8320\t0\t0.1\t1\t1\n10880\t2\t0\t1\t0\n')
            result=runner.gate_audit(path,events,summary,True,12000)
            self.assertEqual(result['forced_releases'],1)
            self.assertEqual(result['state_changes'],1)
            with self.assertRaisesRegex(ValueError,'Closed gate'):
                runner.gate_audit(path,[events[0],dict(events[1],on=1)],summary,True,12000)
            with self.assertRaisesRegex(ValueError,'matching gate'):
                runner.gate_audit(path,[dict(events[0],source_end=9000)],summary,True,12000)
            with self.assertRaisesRegex(ValueError,'counters'):
                runner.gate_audit(path,events,dict(summary,gate_forced_releases=0),True,12000)
            for old,new in (('10880\t2','10880\t4'),('0.1','nan'),('8320','13000')):
                original=path.read_text();path.write_text(original.replace(old,new))
                with self.assertRaises(ValueError): runner.gate_audit(path,events,summary,True,12000)
                path.write_text(original)

    def test_off_power_and_model_coverage_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gate.tsv'
            path.write_text('source_end\tframe\tpower\tenabled\topen\n8320\t0\t0\t0\t1\n')
            summary=dict(model_calls=1,gate_closed_frames=0,gate_forced_releases=0,
                         gate_enabled=False,gate_threshold_db=-60.0)
            self.assertTrue(runner.gate_audit(path,[],summary,False,9000)['pass_'])
            with self.assertRaisesRegex(ValueError,'cover all'):
                runner.gate_audit(path,[],dict(summary,model_calls=2),False,9000)
            path.write_text(path.read_text().replace('\t0\t0\t1','\t0.1\t0\t1'))
            with self.assertRaises(ValueError): runner.gate_audit(path,[],summary,False,9000)

    def test_actual_noteons_use_label_intervals_not_occupancy_segments(self):
        labels=[dict(label_index=8,midi_note=48,start_sample=96,end_sample=192)]
        events=[dict(kind='on',note=48,emitted_ns=t) for t in (999999,1000000,1500000,2000000)]
        events.append(dict(kind='off',note=48,emitted_ns=1600000))
        measured=runner.note_on_counts(events,labels,96000)
        self.assertEqual(measured['total'],4)
        self.assertEqual(measured['labels'][0]['accepted_note_ons'],3)

    def test_complete_runtime_and_lossless_verdict_are_separate(self):
        rows={name:dict(arms={arm:dict(state='measured',integration_pass=True,quality_pass=False)
                            for arm in runner.ARMS},
                       on_vs_off=dict(component_delivery=dict(no_pitch_safety_regression=False)))
              for name in runner.CORPUS}
        result=runner.screen(rows)
        self.assertTrue(result['component_integration_pass'])
        self.assertEqual(result['arms_measured'],24)
        self.assertFalse(result['on_vs_off_lossless_pass'])
        self.assertFalse(result['on_vs_current_replacement_pass'])
        self.assertFalse(result['promotion_accepted'])
        incomplete=copy.deepcopy(rows);del incomplete[runner.CORPUS[0]]['arms']['on']
        self.assertFalse(runner.screen(incomplete)['component_integration_pass'])
        rows[runner.CORPUS[0]]['arms']['on']['integration_pass']=False
        self.assertFalse(runner.screen(rows)['component_integration_pass'])

    def test_remote_guard_precedes_file_access(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
            with self.assertRaises(RuntimeError): runner.run(*[Path('/must-not-open')]*8)
            with self.assertRaises(RuntimeError): runner.measure(*[Path('/must-not-open')]*8)

    def test_frozen_spec_matches_driver(self):
        spec=json.loads((Path(__file__).resolve().parents[1]/'docs/recovery/neural-quiet-gate-20261121.json').read_text())
        self.assertEqual(spec['gate_settings'],runner.GATE)
        self.assertEqual(tuple(spec['datasets']),runner.CORPUS)
        self.assertEqual(len(spec['artifacts']['evidence']['files']),12)
        self.assertTrue(all(n.endswith('-generated.tsv.gz') for n in spec['artifacts']['evidence']['files']))


if __name__=='__main__': unittest.main()
