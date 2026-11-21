"""Synthetic supplemental-screen checks; no recording, model or native execution."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.test_midi_lifecycle_analysis import event, label, trace
from tools import portable_neural_corpus as runner


class NeuralCorpusTests(unittest.TestCase):
    def baseline(self, folder, events, *, samples=200, rate=96000, count=None):
        snapshot, midi = folder/'snapshot.tsv', folder/'midi.tsv'
        snapshot.write_text('samples\tsample_rate\ttransitions\n'
                            f'{samples}\t{rate}\t{len(events) if count is None else count}\n')
        trace(midi, events)
        return runner.baseline_measurement(snapshot, midi, [label(end=200)],
                                          dict(sample_count=200, sample_rate=96000))

    def test_raw_ownership_checked_before_pitch_deduplication_and_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            result=self.baseline(folder,[event(20,'on'),event(50,'on',voice=1),event(90,'off')])
            self.assertEqual(result['compact']['present_pitch_samples'],180)
            self.assertEqual(result['compact']['expected_pitch_samples'],180)
            self.assertEqual(result['event_audit']['raw_note_ons'],2)
            self.assertEqual(len(result['event_audit']['open_at_recording_end']),1)
            self.assertEqual(len(result['snapshot_sha256']),64)
            with self.assertRaisesRegex(ValueError,'pairing'):
                self.baseline(folder,[event(20,'on'),event(30,'on')])

    def test_incomplete_or_different_reference_clock_cannot_be_compared(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for changes in ({'samples':199},{'rate':48000},{'count':2}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.baseline(folder,[event(20,'on')],**changes)

    def test_missing_dataset_and_integration_quality_are_independent(self):
        rows={name:dict(neural=dict(state='measured',integration_pass=True,quality_pass=True))
              for name in runner.CORPUS}
        self.assertTrue(runner.screen(rows)['component_integration_pass'])
        self.assertTrue(runner.screen(rows)['supplemental_noninferiority_pass'])
        self.assertFalse(runner.screen(rows)['promotion_accepted'])
        lost=copy.deepcopy(rows)
        del lost[runner.CORPUS[-1]]
        self.assertFalse(runner.screen(lost)['component_integration_pass'])
        self.assertFalse(runner.screen(lost)['supplemental_noninferiority_pass'])
        rows[runner.CORPUS[0]]['neural']['quality_pass']=False
        self.assertTrue(runner.screen(rows)['component_integration_pass'])
        self.assertFalse(runner.screen(rows)['supplemental_noninferiority_pass'])
        rows[runner.CORPUS[0]]['neural'].update(state='component_execution_failed',integration_pass=False)
        self.assertFalse(runner.screen(rows)['component_integration_pass'])
        self.assertEqual(runner.screen(rows)['datasets_measured'],11)

    def test_local_execution_refused_before_file_access(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
            with self.assertRaises(RuntimeError): runner.run(*[Path('/must-not-open')]*9)
            with self.assertRaises(RuntimeError): runner.measure(*[Path('/must-not-open')]*7)

    def test_cli_distinguishes_measured_quality_rejection_from_component_failure(self):
        for passed in (False,True):
            result=dict(state='completed',screen=dict(component_integration_pass=passed,
                supplemental_noninferiority_pass=False,promotion_accepted=False))
            script='''import json,sys
from unittest.mock import patch
from tools import portable_neural_corpus as runner
args=[v for key in ('spec-path','inputs','model-checkout','replay','harness','bundle','output','cropped-model','crop-report') for v in ('--'+key,'/unused')]
with patch.object(runner,'run',return_value=json.loads(sys.argv[1])):
    raise SystemExit(runner.main(args))
'''
            process=subprocess.run([sys.executable,'-c',script,json.dumps(result)],
                cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,check=False)
            self.assertEqual(process.returncode,0 if passed else 1,process.stderr)
            self.assertEqual(json.loads(process.stdout)['screen'],result['screen'])


if __name__=='__main__': unittest.main()
