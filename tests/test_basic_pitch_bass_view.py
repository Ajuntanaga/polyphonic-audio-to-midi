"""Synthetic FIR, scheduling and ownership checks; no model or recorded audio."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from tools.basic_pitch_bass_view import BassResampler, mapped_bass_event, stream_pair
from tools.basic_pitch_streaming import CausalResampler, stream_blocks


class FakeBackend:
    def __init__(self, full=False, pitches=(60,)):
        self.full, self.pitches, self.windows = full, pitches, []

    def predict(self, window):
        self.windows.append(window.copy())
        notes = np.zeros((172 if self.full else 2,88),dtype=np.float32)
        onsets = np.zeros_like(notes)
        for note in self.pitches:
            notes[:,note-21] = .8
            onsets[:,note-21] = .8
        return notes,onsets


class BassViewTests(unittest.TestCase):
    def test_fir_prefix_partial_eof_and_no_future(self):
        from scipy.signal import upfirdn
        source = np.random.default_rng(11).normal(0,.1,32005).astype(np.float32)
        resampler = BassResampler()
        pieces = [resampler.consume(source[i:i+1280]) for i in range(0,len(source),1280)]
        actual = np.concatenate(pieces)
        expected = upfirdn(resampler.h,source,up=147,down=1280)[:len(actual)]
        np.testing.assert_allclose(actual,expected,atol=1e-7,rtol=1e-6)
        self.assertEqual(len(pieces[-1]),1)
        changed = source.copy(); changed[1280:] += 100
        np.testing.assert_array_equal(BassResampler().consume(changed[:1280]),actual[:147])
        with self.assertRaises(ValueError): resampler.consume(source[:1280])

    def test_both_windows_are_past_only_and_reference_sequence_is_unchanged(self):
        from scipy.signal import upfirdn
        source = np.random.default_rng(12).normal(0,.1,32005).astype(np.float32)
        reference,bass,original = FakeBackend(),FakeBackend(pitches=(71,)),FakeBackend(full=True)
        chunks = lambda: (source[i:i+640] for i in range(0,len(source),640))
        result = stream_pair(chunks(),len(source),reference,bass)
        saved = stream_blocks(chunks(),original)
        for key in ('notes','onsets','frames'):
            np.testing.assert_array_equal(result['reference'][key],saved[key])
        keys = ('kind','note','frame','available_ns')
        self.assertEqual([{k:e[k] for k in keys} for e in result['reference']['events']],
                         [{k:e[k] for k in keys} for e in saved['events']])
        self.assertEqual(len(reference.windows),len(original.windows))
        for a,b in zip(reference.windows,original.windows): np.testing.assert_array_equal(a,b)
        for view,backend,factor,first,resampler in (
                ('reference',reference,1,1860,CausalResampler()),
                ('bass',bass,2,836,BassResampler())):
            direct = upfirdn(resampler.h,source,up=147,down=640*factor)
            for k,window in enumerate(backend.windows):
                end = first+512*k
                expected = np.pad(direct[max(0,end-43844):end],(max(0,43844-end),0))
                np.testing.assert_allclose(window,expected,atol=1e-7,rtol=1e-6)
            rows = result[view]['frames']
            self.assertEqual([r[0] for r in rows],list(range(len(rows))))
            for frame,nominal,end,source_end in rows:
                self.assertLess((end-1)*96000*factor,source_end*22050)
                self.assertIn(end-nominal,(first,first-256))
        self.assertEqual(result['bass']['frames'][0][3],7680)
        self.assertEqual(result['reference']['frames'][0][3],8320)

    def test_disjoint_ownership_and_original_fifo_clock(self):
        source = np.zeros(20000,dtype=np.float32)
        tick = [0]
        def clock():
            tick[0] += 100_000
            return tick[0]
        result = stream_pair((source[i:i+640] for i in range(0,len(source),640)),len(source),
            FakeBackend(pitches=(21,59,60,108)),FakeBackend(pitches=(21,32,33,71,72,108)),clock_ns=clock)
        self.assertEqual(result['combined_open_pitches'],[21,59,60,108])
        self.assertEqual(sorted(e['note'] for e in result['combined_events']),[21,59,60,108])
        timings = {r[0]:r for r in result['timing']}
        for view in ('reference','bass'):
            frames = {r[0]:r for r in result[view]['frames']}
            for event in result[view]['events']:
                row = timings[frames[event['frame']][3]]
                self.assertEqual((event['available_ns'],event['emitted_ns']),(row[1],row[3]))
        self.assertTrue(all(e['emitted_ns']>=e['available_ns'] for e in result['combined_events']))
        self.assertIsNone(mapped_bass_event(dict(kind='on',note=72)))
        self.assertEqual(mapped_bass_event(dict(kind='off',note=71))['note'],59)

    def test_final_odd_phase_is_consumed_and_bad_source_is_rejected(self):
        for size in (640,1280,1920,1925):
            source = np.zeros(size,dtype=np.float32)
            result = stream_pair((source[i:i+640] for i in range(0,size,640)),size,FakeBackend(),FakeBackend())
            self.assertEqual(result['bass']['resampled_samples'],(size*147+1279)//1280)
        with self.assertRaises(ValueError):
            stream_pair([np.zeros(639),np.zeros(640)],1279,FakeBackend(),FakeBackend())
        with self.assertRaises(ValueError):
            stream_pair([np.zeros(640)],1280,FakeBackend(),FakeBackend())

    def test_driver_guard_precedes_inputs_and_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'absent-output'
            run=subprocess.run([sys.executable,'-m','tools.portable_basic_pitch_bass_view',
                '--spec','absent','--inputs','absent','--model-checkout','absent','--output',str(output)],
                capture_output=True,text=True,env={k:v for k,v in os.environ.items() if k!='GITHUB_ACTIONS'})
            self.assertNotEqual(run.returncode,0)
            self.assertIn('requires GitHub Actions',run.stderr)
            self.assertFalse(output.exists())

    def test_quality_gate_separates_recovery_from_false_note_tradeoff(self):
        from tests.test_midi_lifecycle_analysis import label
        from tools.pitch_detector_comparison import compare, score
        from tools.portable_basic_pitch_bass_view import assess, low_pitch_coverage
        labels = [label(0,20,120,note=40),label(1,20,120,note=40),
                  label(2,20,120,note=64)]
        clock = dict(sample_count=200,sample_rate=1000)
        before = [(20,120,64)]
        after = before+[(20,120,40)]
        def dataset(spans):
            delta = compare(score(before,labels,**clock),score(spans,labels,**clock))
            return dict(arms=dict(
                reference_1x=dict(serviced=dict(low_pitch_coverage=low_pitch_coverage(before,labels,clock))),
                combined=dict(serviced=dict(low_pitch_coverage=low_pitch_coverage(spans,labels,clock),
                    comparison_to_current=delta,comparison_to_same_pass_1x=delta))),
                timing=dict(inference_block_service_ns=dict(p99=10000000),
                            queued_before_service_ns=dict(maximum=10000000)))
        low = low_pitch_coverage(after,labels,clock)
        self.assertEqual(low,dict(expected_pitch_samples=100,present_pitch_samples=100,percent=100))
        result = assess(dict(ordinary=dataset(after),extended_middle=dataset(after)))
        self.assertTrue(result['practical_usefulness_pass'])
        self.assertTrue(result['incremental_noninferiority_pass'])
        self.assertEqual(result['previously_zero_low_labels_recovered'],[0,1])
        result = assess(dict(ordinary=dataset(after),extended_middle=dataset(after+[(130,140,40)])))
        self.assertTrue(result['practical_usefulness_pass'])
        self.assertFalse(result['incremental_noninferiority_pass'])
        self.assertFalse(result['strict_current_replacement_pass'])


if __name__=='__main__': unittest.main()
