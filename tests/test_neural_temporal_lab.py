"""Synthetic collection/provenance/decision gates; no corpus or model work."""
import copy
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import portable_neural_temporal_lab as lab
from tools.pitch_detector_comparison import compare, score


class TemporalLabTests(unittest.TestCase):
    def test_remote_guard_precedes_all_file_access(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}), patch.object(Path,'read_text') as read:
            for action, count in ((lab.prepare,2),(lab.run,7)):
                with self.assertRaises(RuntimeError): action(*[Path('/unused')]*count)
            read.assert_not_called()

    def test_selected_archive_hash_size_and_paths_fail_before_extraction(self):
        data=b'model';pin=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'artifact.zip'
            cases=[('nested/model.onnx',dict(pin,sha256='0'*64),False),
                   ('nested/model.onnx',dict(pin,bytes=len(data)+1),False),
                   ('../outside',pin,False),('nested/model.onnx',pin,True)]
            for index,(name,check,symlink) in enumerate(cases):
                with zipfile.ZipFile(archive,'w') as z:
                    entry=zipfile.ZipInfo(name)
                    if symlink:entry.external_attr=(stat.S_IFLNK|0o777)<<16
                    z.writestr(entry,data)
                dest=root/str(index)
                with self.subTest(name=name,symlink=symlink):
                    with self.assertRaises(ValueError):lab.extract_members(archive,{name:check},dest)
                    self.assertFalse(dest.exists())
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('nested/model.onnx',data)
                z.writestr('unrequested.txt',b'do not extract')
            result=lab.extract_members(archive,{'nested/model.onnx':pin},root/'valid')
            self.assertEqual(result,{'nested/model.onnx':pin})
            self.assertEqual((root/'valid/nested/model.onnx').read_bytes(),data)
            self.assertFalse((root/'valid/unrequested.txt').exists())

    def producer(self):
        producer=dict(run_id=12,source_commit='a'*40,worker_commit='b'*40,
                      specification_sha256='c'*64)
        spec=dict(producer=producer,datasets={name:{'pin':name} for name in lab.DATASETS})
        report=dict(schema='m3_basic_pitch_release_adaptation_v1',final=True,state='complete',
            run_id='12',source_commit='a'*40,worker_commit='b'*40,specification_sha256='c'*64,
            specification=dict(streaming=lab.SETTINGS,datasets=spec['datasets']),
            exports={arm:dict(synthetic_parity_pass=True,crop=dict(original_initializers_identical=True,
                     output_contract=dict(frame_origin=164,shape=[1,2,88]))) for arm in lab.ARMS},
            datasets={name:dict(backend_parity={arm:dict(parity_pass=True) for arm in lab.ARMS})
                      for name in lab.DATASETS})
        return report,spec

    def test_completed_workflow_is_insufficient_without_report_identity(self):
        report,spec=self.producer();lab.validate_report(report,spec)
        for path,value in [(('source_commit',),'d'*40),(('final',),False),
            (('exports','release','crop','output_contract','frame_origin'),166),
            (('datasets','ordinary','backend_parity','release','parity_pass'),False)]:
            bad=copy.deepcopy(report);target=bad
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
            with self.subTest(path=path):
                with self.assertRaises(ValueError):lab.validate_report(bad,spec)

    def rows(self,extra_gap=False):
        labels=[dict(label_index=0,start_sample=10,end_sample=90,midi_note=60,string_mask=1)]
        clock=dict(sample_count=100,sample_rate=100)
        baseline=score([(10,50,60)],labels,**clock)
        prior=score([(10,80,60)],labels,**clock)
        release=score([(10,80,60)]+([(90,100,64)] if extra_gap else []),labels,**clock)
        result={}
        for name in lab.DATASETS:
            result[name]={}
            for arm,measurement in (('prior',prior),('release',release)):
                view=dict(measurement=measurement,comparison_to_current=compare(baseline,measurement))
                result[name][arm]=dict(integration_pass=True,formats={fmt:dict(state='measured',
                    views=dict(component_delivery=view)) for fmt in ('32','64')})
        return result

    def test_quality_failure_does_not_become_integration_success_or_promotion(self):
        clean=lab.assess(self.rows());self.assertTrue(clean['strict_pitch_replacement_pass'])
        dirty=lab.assess(self.rows(extra_gap=True))
        self.assertTrue(dirty['component_integration_pass'])
        self.assertFalse(dirty['strict_pitch_replacement_pass'])
        self.assertFalse(dirty['promotion_accepted'])
        rows=self.rows();rows['ordinary']['release']['integration_pass']=False
        rows['ordinary']['release']['formats']['32']=dict(state='crop_identity_failed',integration_pass=False)
        failed=lab.assess(rows)
        self.assertFalse(failed['component_integration_pass'])
        self.assertFalse(failed['strict_pitch_replacement_pass'])


if __name__=='__main__':unittest.main()
