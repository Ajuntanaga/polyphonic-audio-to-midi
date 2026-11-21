"""Fixed-readout causal checks on synthetic arrays only."""
from copy import deepcopy
from itertools import count
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from tools.basic_pitch_context import context_measurements, context_screen, reference_identity, save_context
from tools.basic_pitch_streaming import stream_blocks
from tools.pitch_detector_comparison import score


class FrameBackend:
    def __init__(self):
        self.windows = []

    def predict(self, window):
        frame = np.arange(172) + 2*len(self.windows) - 164
        self.windows.append(window.copy())
        notes = np.zeros((172,88), dtype=np.float32)
        onsets = notes.copy()
        notes[:,39] = np.clip(frame/100, 0, 1)
        onsets[frame == 4,39] = .9
        notes[frame == 4,39] = .5
        return notes, onsets


def synthetic(backend, paired=True, length=32005):
    source = np.zeros(length, dtype=np.float32)
    return stream_blocks((source[i:i+640] for i in range(0,len(source),640)), backend,
                         clock_ns=lambda c=count(step=100): next(c),
                         additional_readout_start=160 if paired else None)


class ContextTests(unittest.TestCase):
    def test_same_inference_frames_delayed_not_backdated(self):
        original_backend, paired_backend = FrameBackend(), FrameBackend()
        original, paired = synthetic(original_backend,False), synthetic(paired_backend)
        for old,new in zip(original_backend.windows,paired_backend.windows):
            np.testing.assert_array_equal(old,new)
        self.assertEqual(original['model_calls'],paired['model_calls'])
        for key in ('notes','onsets','frames','events'):
            np.testing.assert_equal(original[key],paired[key])
        extra = paired['additional_readout']
        self.assertEqual(len(extra['frames']),len(paired['frames'])-4)
        np.testing.assert_array_equal(extra['notes'],paired['notes'][:-4])
        self.assertEqual([r[0] for r in extra['frames']],list(range(len(extra['frames']))))
        for row,old in zip(extra['frames'],paired['frames']):
            self.assertEqual(row[:2],old[:2])
            self.assertEqual(row[2]-old[2],1024)
            self.assertIn(row[2]-row[1],(2884,2628))
            self.assertLess((row[2]-1)*96000,row[3]*22050)
        on = next(e for e in extra['events'] if e['kind']=='on')
        before = next(e for e in paired['events'] if e['kind']=='on')
        self.assertEqual(on['frame'],before['frame'])
        self.assertGreater(on['available_ns'],before['available_ns'])
        self.assertGreaterEqual(on['emitted_ns'],on['available_ns'])

    def test_decoders_are_independent_and_short_input_has_no_candidate_frame(self):
        class EarlierOnly:
            def predict(self,window):
                notes = np.zeros((172,88),dtype=np.float32)
                notes[160:162,39] = .9
                return notes, notes.copy()
        result = synthetic(EarlierOnly())
        self.assertEqual(result['events'],[])
        self.assertEqual(result['open_decoder_pitches'],[])
        self.assertEqual(result['additional_readout']['open_decoder_pitches'],[60])
        short = synthetic(EarlierOnly(),length=10000)
        self.assertEqual(short['model_calls'],1)
        self.assertEqual(short['additional_readout']['events'],[])
        self.assertEqual(short['additional_readout']['notes'].shape,(0,88))

    def test_invalid_readout_fails_before_consuming_input(self):
        def forbidden():
            raise AssertionError('Input consumed before validation')
            yield
        for start in (-2,159,164,165,160.,True):
            with self.subTest(start=start), self.assertRaises(ValueError):
                stream_blocks(forbidden(),FrameBackend(),additional_readout_start=start)

    def test_reference_identity_allows_only_worker_timing_change(self):
        result = synthetic(FrameBackend())
        arrays = dict(note=result['notes'].copy(),onset=result['onsets'].copy(),
                      frames=np.asarray(result['frames']))
        saved = dict(events=deepcopy(result['events']),cleanup=dict(notes=result['open_decoder_pitches']))
        saved['events'][0]['emitted_ns'] += 12345
        self.assertTrue(all(reference_identity(result,arrays,saved).values()))
        arrays['note'][0,0] += .1
        self.assertFalse(reference_identity(result,arrays,saved)['notes'])
        saved['events'][0]['available_ns'] += 1
        self.assertFalse(reference_identity(result,arrays,saved)['events_and_availability'])
        arrays['frames'][0,2] += 1
        self.assertFalse(reference_identity(result,arrays,saved)['frames'])
        saved['cleanup']['notes'] = [61]
        self.assertFalse(reference_identity(result,arrays,saved)['cleanup_state'])

    def test_full_recording_and_labels_remain_in_candidate_score(self):
        clock = dict(sample_count=9600,sample_rate=96000)
        labels = [dict(label_index=0,start_sample=0,end_sample=9600,midi_note=60,string_mask=1)]
        baseline = score([(0,9600,60)],labels,**clock)
        event = dict(kind='on',note=60,frame=0,available_ns=10_000_000,emitted_ns=11_000_000)
        result = dict(events=[event],additional_readout=dict(events=[]))
        measured = context_measurements(result,labels,clock,baseline,baseline)
        for view in measured.values():
            self.assertFalse(view['comparison_to_same_pass_reference']['no_pitch_safety_regression'])
            totals = view['measurement']['pitch_sets']['totals']
            self.assertEqual(totals['expected_pitch_samples'],9600)
            self.assertEqual(totals['present_pitch_samples'],0)

    def test_incremental_screen_requires_gain_and_both_safety_gates(self):
        def rows(gain,safe):
            return {'context_candidate':{'serviced':{'comparison_to_same_pass_reference':{
                'pitch_coverage_gain_pp':gain,'no_pitch_safety_regression':safe}}}}
        data = {'ordinary':rows(1,True),'extended-middle':rows(0,True)}
        self.assertTrue(context_screen(data)['incremental_context_screen_pass'])
        data['extended-middle'] = rows(0,False)
        self.assertFalse(context_screen(data)['incremental_context_screen_pass'])
        data = {'ordinary':rows(0,True),'extended-middle':rows(0,True)}
        self.assertFalse(context_screen(data)['incremental_context_screen_pass'])

    def test_saved_artifacts_and_report_use_the_same_candidate(self):
        result = synthetic(FrameBackend())
        clock = dict(sample_count=32005,sample_rate=96000)
        labels = [dict(label_index=0,start_sample=0,end_sample=32005,midi_note=60,string_mask=1)]
        baseline = score([],labels,**clock)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            np.savez_compressed(root/'ordinary-stream.npz',note=result['notes'],onset=result['onsets'],
                frames=np.asarray(result['frames'],dtype='int64'),timing=np.asarray(result['timing'],dtype='int64'))
            (root/'ordinary-events.json').write_text(json.dumps(dict(events=result['events'],
                cleanup=dict(notes=result['open_decoder_pitches']))))
            report = save_context('ordinary',result,labels,clock,baseline,baseline,root,root)
            self.assertTrue(all(report['reference_identity'].values()))
            self.assertEqual(report['fewer_positive_tail_frames_than_reference'],4)
            with np.load(root/'ordinary-context.npz',allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['note'],result['additional_readout']['notes'])
                np.testing.assert_array_equal(saved['frames'],result['additional_readout']['frames'])
            events = json.loads((root/'ordinary-context-events.json').read_text())
            self.assertEqual(events['events'],result['additional_readout']['events'])
            self.assertEqual(report['serviced'],context_measurements(result,labels,clock,baseline,baseline)['serviced'])


if __name__ == '__main__':
    unittest.main()
