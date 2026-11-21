"""Synthetic arrays/intervals only; no recordings, fitting or model inference."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from tests.test_midi_lifecycle_analysis import label
from tools.basic_pitch_temporal_reliability import (calibration_cutoff,
    causal_features, decision_intervals, full_interval_targets, occupancy_spans,
    passage_split, region_inputs)
from tools.portable_basic_pitch_temporal_reliability import evaluate_region, verify_purges


class TemporalReliabilityTests(unittest.TestCase):
    def test_features_do_not_read_future_frames(self):
        rng = np.random.default_rng(72)
        note = rng.random((25, 88), dtype=np.float32)
        onset = rng.random((25, 88), dtype=np.float32)
        original, names = causal_features(note, onset)
        note[13:] = 100
        onset[13:] = 200
        changed, _ = causal_features(note, onset)
        np.testing.assert_array_equal(original[:13], changed[:13])
        self.assertEqual(original.shape, (25, 88, 76))
        self.assertEqual(len(set(names)), 76)

    def test_harmonic_offsets_have_correct_direction_and_zero_edges(self):
        note = np.zeros((20, 88), dtype=np.float32)
        note[0, 10] = 0.8
        features, names = causal_features(note, np.zeros_like(note))
        self.assertAlmostEqual(float(features[0, 22, names.index('note_offset-12_now')]), .8)
        self.assertEqual(features[0, 0, names.index('note_offset-12_now')], 0)
        self.assertAlmostEqual(float(features[7, 22, names.index('note_offset-12_max8')]), .8)
        self.assertEqual(features[8, 22, names.index('note_offset-12_max8')], 0)
        self.assertAlmostEqual(float(features[16, 10, names.index('note_lag16')]), .8)

    def test_same_call_frames_share_one_interval_at_completion(self):
        frames = np.array([[0, 0, 100, 640], [1, 256, 100, 640],
                           [2, 512, 200, 1280], [3, 768, 200, 1280]], dtype=np.int64)
        timing = np.zeros((2, 9), dtype=np.int64)
        timing[:, 0] = [640, 1280]
        timing[:, 3] = [1000001, 2000001]
        indices, starts, ends = decision_intervals(frames, timing, 300)
        self.assertEqual(indices.tolist(), [1, 3])
        self.assertEqual(starts.tolist(), [97, 193])
        self.assertEqual(ends.tolist(), [193, 300])
        timing[1, 3] = 1
        with self.assertRaises(ValueError):
            decision_intervals(frames, timing, 300)

    def test_targets_keep_partial_boundary_intervals_negative(self):
        starts, ends = np.array([0, 10, 20, 30]), np.array([10, 20, 30, 40])
        labels = [label(0, 5, 20, note=60), label(1, 20, 35, note=60)]
        target = full_interval_targets(starts, ends, labels, 40)
        self.assertEqual(target[:, 39].tolist(), [False, True, True, False])
        self.assertEqual(target.sum(), 2)

    def test_cutoff_only_uses_calibration_negatives_and_breaks_ties(self):
        p = np.array([[.2, .4], [.8, .6], [.999, .999]])
        y = np.array([[True, False], [True, False], [False, False]])
        mask = np.array([True, True, False])
        cutoff = calibration_cutoff(p, y, mask)
        self.assertGreater(cutoff, .6)
        self.assertLess(cutoff, .8)
        p[2] = 0
        self.assertEqual(cutoff, calibration_cutoff(p, y, mask))
        p[1, 1] = 1
        self.assertGreater(calibration_cutoff(p, y, mask), 1)

    def test_passage_split_purges_whole_passages_and_no_labels_are_cut(self):
        labels = [label(i, 10+i*100, 90+i*100, note=60+i) for i in range(10)]
        split = passage_split(labels, 1000, sample_rate=100,
                              train_passages=4, calibration_end=7, purge_seconds=1)
        self.assertEqual(split['regions'], dict(train=(0, 400), calibration=(500, 700), test=(800, 1000)))
        self.assertEqual(split['label_indices'], dict(train=[0, 1, 2, 3], calibration=[5, 6], test=[8, 9]))
        for left, right in split['regions'].values():
            region_inputs([], labels, left, right)
        with self.assertRaises(ValueError):
            region_inputs([], labels, 50, 1000)

    def test_context_purge_fails_when_oldest_feature_window_reaches_train(self):
        data = dict(starts=np.array([400000, 800000]), ends=np.array([410000, 810000]),
                    indices=np.array([16, 17]), arrays=dict(frames=np.zeros((18, 4), dtype=np.int64)))
        data['arrays']['frames'][:, 2] = 200000
        split = dict(regions=dict(train=(0, 100000), calibration=(400000, 500000), test=(800000, 900000)))
        self.assertTrue(verify_purges(data, split)['test']['disjoint'])
        data['arrays']['frames'][0, 2] = 43844
        with self.assertRaisesRegex(ValueError, 'context crosses'):
            verify_purges(data, split)

    def test_added_occupancy_merges_and_union_cannot_hide_false_notes(self):
        p = np.zeros((3, 88))
        p[:2, 39] = .9
        p[1, 43] = .9
        spans = occupancy_spans(p, .8, np.array([10, 20, 30]), np.array([20, 30, 40]), 50)
        self.assertEqual(spans, [(10, 30, 60), (20, 30, 64)])
        data = dict(clock=dict(sample_count=50, sample_rate=1000),
                    current=[(10, 40, 60)], labels=[label(0, 10, 40)])
        result = evaluate_region(data, spans, 0, 50)
        self.assertEqual(result['comparison']['label_deltas'][0]['present_samples_delta'], 0)
        self.assertFalse(result['comparison']['no_pitch_safety_regression'])
        self.assertEqual(result['comparison']['sample_deltas']['extra_pitch_voice_samples'], 10)

    def test_remote_guard_precedes_file_access_and_fitting(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_basic_pitch_temporal_reliability',
                '--spec', 'absent', '--output', str(output)], text=True, capture_output=True,
                env={k: v for k, v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
