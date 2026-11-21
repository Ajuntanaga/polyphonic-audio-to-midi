"""Synthetic clock/interval checks only; never opens a recorded cache."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_basic_pitch_streaming import activation
from tests.test_midi_lifecycle_analysis import label
from tools.basic_pitch_cached_diagnosis import (bridge_comparisons, clip_labels,
    clip_spans, common_horizon, decode_cached, frame_event_spans,
    indexed_note_spans, nominal_model_sample, nominal_source_sample,
    offline_note_frames, unique_time_index, upstream_frame_times)
from tools.pitch_detector_comparison import compare, score


class CachedBridgeTests(unittest.TestCase):
    def test_window_boundary_preserves_trimmed_window_hop(self):
        self.assertEqual(nominal_model_sample(141, 'offline_window'), 36096)
        self.assertEqual(nominal_model_sample(142, 'offline_window'), 36164)
        self.assertEqual(nominal_model_sample(143, 'offline_window'), 36420)
        self.assertEqual(nominal_model_sample(142, 'stream'), 36352)
        self.assertEqual(nominal_source_sample(142, 'offline_window'), 157449)
        with self.assertRaises(ValueError):
            nominal_model_sample(-1, 'stream')

    def test_original_timestamp_staircase_is_kept_separate(self):
        times = upstream_frame_times(345)
        self.assertAlmostEqual(times[142], 142*256/22050)
        offset = 188/22050 + .0018
        self.assertAlmostEqual(times[172], 172*256/22050-offset)
        self.assertAlmostEqual(times[344], 344*256/22050-2*offset)
        self.assertGreater(times[172], times[171])
        self.assertNotEqual(times[172], nominal_model_sample(172, 'offline_window')/22050)

    def test_saved_endpoints_invert_uniquely_without_fitted_shift(self):
        times = upstream_frame_times(345)
        indexed, audit = offline_note_frames([
            [times[141], times[173], 60, .5, None],
            [times[0], times[344], 72, .3, []]], 345)
        self.assertEqual(indexed, [(141,173,60), (0,344,72)])
        self.assertEqual(audit['maximum_error_seconds'], 0)
        self.assertEqual(audit['endpoints'], 4)
        with self.assertRaises(ValueError):
            unique_time_index(times[10]+.001, times)
        with self.assertRaises(ValueError):
            unique_time_index(.1, [.1, .1])

    def test_redecode_keeps_forward_hysteresis_and_open_eof(self):
        pairs = [activation(value=v) for v in (.4,.4,.4,0,0,0,.4,.4,.4)]
        events, opened = decode_cached([p[0] for p in pairs], [p[1] for p in pairs])
        self.assertEqual(events, [dict(kind='on',note=60,frame=2),
            dict(kind='off',note=60,frame=5), dict(kind='on',note=60,frame=8)])
        self.assertEqual(opened, [60])
        spans, audit = frame_event_spans(events, 'stream', 10000)
        self.assertEqual(spans, [(2229,5573,60), (8916,10000,60)])
        self.assertEqual(audit['decoder_open_pitches'], [60])
        with self.assertRaises(ValueError):
            frame_event_spans([dict(kind='off',note=60,frame=0)], 'stream', 10000)

    def test_common_horizon_clips_every_arm_and_labels(self):
        horizon = common_horizon(400000, 142, 142)
        self.assertEqual(horizon, nominal_source_sample(142, 'offline_window'))
        labels, audit = clip_labels([label(0,10,30), label(1,40,60), label(2,70,90)], 50)
        self.assertEqual([(r['label_index'], r['start_sample'], r['end_sample'])
                          for r in labels], [(0,10,30), (1,40,50)])
        self.assertEqual(audit, dict(original_label_indices=[0,1],
            removed_label_samples=30, wholly_outside_labels=1))
        self.assertEqual(clip_spans([(20,60,60),(70,90,72)],50),[(20,50,60)])
        self.assertEqual(indexed_note_spans([(0,142,60)],'offline_window',horizon),
                         [(0,horizon,60)])

    def test_signed_bridges_reconcile_gains_losses_and_false_outputs(self):
        labels = [label(0,20,120)]
        clock = dict(sample_count=200,sample_rate=1000)
        arms = dict(A=[(50,150,60)], B=[(40,140,60)], C=[(30,130,60)],
                    D=[(20,120,60),(70,90,72)], E=[(10,120,60)], F=[(20,119,60)])
        measured = {key:score(value,labels,**clock) for key,value in arms.items()}
        bridges = bridge_comparisons(measured)
        direct = compare(measured['A'],measured['F'])
        self.assertEqual(sum(r['comparison']['sample_deltas']['present_pitch_samples']
                             for r in bridges.values()),29)
        self.assertEqual(direct['sample_deltas']['present_pitch_samples'],29)
        self.assertEqual(sum(r['comparison']['extra_gap_pitch_samples_delta']
                             for r in bridges.values()),-30)

    def test_remote_guard_precedes_cache_and_output_access(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'absent-output'
            result = subprocess.run([sys.executable,'-m','tools.portable_basic_pitch_cached_diagnosis',
                '--spec','absent','--output',str(output)],capture_output=True,text=True,
                env={k:v for k,v in os.environ.items() if k!='GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode,0)
            self.assertIn('requires GitHub Actions',result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
