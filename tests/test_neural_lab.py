"""Synthetic delivery and deadline checks; no audio or native execution."""
import os
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from tools.portable_neural_lab import LAB,join_delivery,run,timing_report


class LabReportTests(unittest.TestCase):
    def fixture(self):
        generated=[dict(frame=0,note=60,on=1,source_end=640,ready_ns=7_000_000),
                   dict(frame=1,note=64,on=1,source_end=1280,ready_ns=14_000_000)]
        delivered=[dict(note=60,on=1,host_sample=512,emitted_ns=8_000_000,cleanup=0),
                   dict(note=64,on=1,host_sample=1024,emitted_ns=15_000_000,cleanup=0),
                   dict(note=60,on=0,host_sample=1280,emitted_ns=16_000_000,cleanup=1),
                   dict(note=64,on=0,host_sample=1280,emitted_ns=16_000_001,cleanup=1)]
        return generated,delivered

    def test_callback_clock_not_source_offset_and_all_cleanup(self):
        generated,delivered=self.fixture()
        events,audit=join_delivery(generated,delivered,1280)
        self.assertEqual(events[0]['emitted_ns'],8_000_000)
        self.assertEqual(events[0]['available_ns'],6_666_667)
        self.assertEqual(audit['cleanup_notes'],[60,64])
        self.assertEqual(audit['active_after_cleanup'],0)

    def test_lost_reordered_or_backdated_output_rejected(self):
        generated,delivered=self.fixture()
        variants=[delivered[:-1],delivered[1:],
            [dict(delivered[0],emitted_ns=6_999_999)]+delivered[1:],
            [dict(delivered[0],note=61)]+delivered[1:],
            delivered[:2]+[dict(delivered[2],on=1)]+delivered[3:]]
        for rows in variants:
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError): join_delivery(generated,rows,1280)

    def test_ready_event_still_cannot_precede_source_availability(self):
        generated,delivered=self.fixture()
        generated[0]['ready_ns']=1
        delivered[0]['emitted_ns']=1
        with self.assertRaises(ValueError): join_delivery(generated,delivered,1280)

    def test_variable_period_deadline_allocations_and_backlog(self):
        callbacks=[dict(samples=n,duration_ns=100,late_ns=0,allocations=0,frees=0)
                   for n in (0,32,512,1024)]
        workers=[dict(service_ns=10_000_000,queued_ns=100,model_ns=9_000_000)]
        self.assertTrue(all(timing_report(callbacks,workers)['gates'].values()))
        bad=[dict(callbacks[1],duration_ns=333335,allocations=1,frees=1)]+callbacks[1:]
        gates=timing_report(bad,workers)['gates']
        for key in ('callback_max','callback_zero_allocations','callback_zero_deallocations',
                    'callback_zero_overruns','callback_audio_period'):
            self.assertFalse(gates[key],key)
        self.assertFalse(timing_report(callbacks,[dict(workers[0],queued_ns=LAB['backlog_max_limit_ns']+1)])
                         ['gates']['worker_maximum_backlog'])
        self.assertFalse(timing_report(callbacks[:-1],workers)['gates']['variable_callback_sizes'])

    def test_local_driver_fails_before_opening_files(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
            with self.assertRaises(RuntimeError): run(*[Path('/must-not-open')]*6)

    def test_cli_fails_component_gates_but_keeps_quality_verdict_separate(self):
        # Exercise the CLI's actual process exit after its report has returned.
        # No runner, model, harness or recording is executed in this test.
        for state,passed in (('component_execution_failed',False),('measured',False),('measured',True)):
            result=dict(state='completed',screen=dict(component_integration_pass=passed,
                strict_pitch_replacement_pass=False),datasets={'ordinary':{'formats':{'32':{'state':state}}}})
            script='''import json, sys
from unittest.mock import patch
from tools import portable_neural_lab as lab
args = [v for key in ('spec-path','inputs','model-checkout','harness','bundle','output') for v in ('--'+key,'/unused')]
with patch.object(lab, 'run', return_value=json.loads(sys.argv[1])):
    raise SystemExit(lab.main(args))
'''
            with self.subTest(state=state,passed=passed):
                process=subprocess.run([sys.executable,'-c',script,json.dumps(result)],
                    cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,check=False)
                self.assertEqual(process.returncode,0 if passed else 1,process.stderr)
                self.assertEqual(json.loads(process.stdout)['screen'],result['screen'])


if __name__=='__main__': unittest.main()
