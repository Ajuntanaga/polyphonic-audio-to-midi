"""Frozen comparison and failure gates; no recording or model access."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.portable_basic_pitch_shorter_lookahead import ARMS, assess, run, validate_spec
from tools.portable_basic_pitch_temporal_crop import ReadoutBackend


class ShorterLookaheadTest(unittest.TestCase):
    def test_frozen_specification(self):
        path=Path(__file__).resolve().parents[1]/'docs/recovery/basic-pitch-shorter-lookahead-20261122.json'
        spec=json.loads(path.read_text())
        validate_spec(spec)
        for key,value in [('max_absolute',.001),('readouts',[164,168]),
                          ('arms',['control164','candidate166']),
                          ('queue_max_limit_ns',30_000_000),
                          ('service_p99_limit_ns',21_000_000)]:
            changed=copy.deepcopy(spec)
            changed[key]=value
            with self.assertRaises(ValueError):
                validate_spec(changed)

    def test_integrity_runtime_and_quality_are_separate_required_gates(self):
        row=dict(arms={arm:dict(timing=dict(
            inference_block_service_ns=dict(p99=20_000_000),
            queued_before_service_ns=dict(maximum=26_666_667))) for arm in ARMS},
            control_reference_parity=dict(parity_pass=True),
            candidate_reference_parity=dict(parity_pass=True),
            candidate_source_availability_scores_identical=True,
            primary_comparison=dict(no_pitch_safety_regression=True))
        data={name:copy.deepcopy(row) for name in ('ordinary','extended-middle')}
        self.assertTrue(assess(data,True)['shorter_lookahead_screen_pass'])
        self.assertFalse(assess(data,True)['promotion_accepted'])
        self.assertFalse(assess(data,True)['prior_adaptation_quality_pass'])
        self.assertFalse(assess(data,False)['shorter_lookahead_screen_pass'])
        for parity in ('control_reference_parity','candidate_reference_parity'):
            changed=copy.deepcopy(data)
            changed['ordinary'][parity]['parity_pass']=False
            self.assertFalse(assess(changed,True)['shorter_lookahead_screen_pass'])
        changed=copy.deepcopy(data)
        changed['extended-middle']['candidate_source_availability_scores_identical']=False
        self.assertFalse(assess(changed,True)['shorter_lookahead_screen_pass'])
        for arm in ('control164','candidate166'):
            changed=copy.deepcopy(data)
            changed['ordinary']['arms'][arm]['timing']['inference_block_service_ns']['p99']+=1
            self.assertFalse(assess(changed,True)['shorter_lookahead_screen_pass'])
        changed=copy.deepcopy(data)
        changed['ordinary']['primary_comparison']['no_pitch_safety_regression']=False
        result=assess(changed,True)
        self.assertTrue(result['reference_and_crop_integrity_pass'])
        self.assertTrue(result['cropped_cpu_feasibility_pass'])
        self.assertFalse(result['shorter_lookahead_screen_pass'])
        del data['extended-middle']['arms']['reference166']
        self.assertFalse(assess(data,True)['shorter_lookahead_screen_pass'])

    def test_remote_guards_precede_paths_and_model_loading(self):
        with patch.dict('os.environ',{'GITHUB_ACTIONS':'false'}):
            with self.assertRaises(RuntimeError):
                run(Path('not-read'),Path('not-created'))
            with self.assertRaises(RuntimeError):
                ReadoutBackend(Path('not-read'),readout_start=166)


if __name__=='__main__':
    unittest.main()
