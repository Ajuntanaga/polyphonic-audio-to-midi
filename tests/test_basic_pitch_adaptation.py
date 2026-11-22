import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from tools.basic_pitch_adaptation import (SETTINGS, component_frames, frame_summary,
    paired_source_results, render_window, representation_gate, resampled_length, window_plan)
from tools.basic_pitch_streaming import SETTINGS as STREAMING


class AdaptationTest(unittest.TestCase):
    def takes(self):
        return [dict(key=f'{role}:{i}', role=role, string_mask=1 << i, midi_note=40+i,
                     start_sample=0, end_sample=96000 if i % 2 else 288000)
                for role in ('train', 'calibration', 'test') for i in range(8)]

    def test_plan_keeps_every_take_in_its_role(self):
        for role in ('train', 'calibration', 'test'):
            plan = window_plan(self.takes(), role, 80, 123)
            self.assertEqual(plan, window_plan(self.takes(), role, 80, 123))
            used = {c['source_key'] for row in plan for c in row['components']}
            self.assertEqual(used, {f'{role}:{i}' for i in range(8)})
            anchors = [r for r in plan if r.get('anchored_singleton')]
            self.assertEqual(len(anchors), 8)
            self.assertTrue(all(len(r['components']) == 1 for r in anchors))
            for row in plan:
                masks = [c['string_mask'] for c in row['components']]
                self.assertEqual(len(masks), len(set(masks)))
                for c in row['components']:
                    self.assertGreater(c['length'], 0)
                    self.assertLessEqual(c['placement']+c['length'], 43844)

    def test_short_note_mask_and_silence_are_not_full_window_labels(self):
        c = dict(source_key='a', note=60, string_mask=1, crop_begin=0,
                 length=1000, placement=512, gain_db=0)
        row = dict(gain_db=0, components=[c])
        signal, truth, levels = render_window(row, {'a': np.ones(1000)})
        self.assertEqual(np.flatnonzero(truth[:, 39]).tolist(), [2, 3, 4, 5])
        self.assertEqual(int(truth.sum()), 4)
        self.assertFalse(signal[:512].any())
        self.assertFalse(signal[1512:].any())
        self.assertAlmostEqual(levels[0]['crop_rms'], 1)
        silence, labels, _ = render_window(dict(gain_db=0, components=[]), {})
        self.assertFalse(silence.any())
        self.assertFalse(labels.any())
        self.assertEqual(resampled_length(96000), 22050)

    def test_unison_is_one_pitch_not_two(self):
        c = dict(source_key='a', note=60, string_mask=1, crop_begin=0,
                 length=1000, placement=0, gain_db=0)
        row = dict(gain_db=0, components=[c, dict(c, source_key='b', string_mask=2)])
        _, truth, _ = render_window(row, {'a': np.ones(1000), 'b': np.ones(1000)})
        self.assertEqual(int(truth.sum()), 4)

    def test_per_occurrence_loss_cannot_hide_in_aggregate(self):
        c = dict(source_key='a', note=60, string_mask=1, crop_begin=0,
                 length=43844, placement=0, gain_db=0)
        plan = [dict(components=[c]), dict(components=[c])]
        before = np.zeros((2, 172, 88), np.float32)
        after = before.copy()
        before[0, :20, 39] = 1
        after[0, :19, 39] = 1
        after[1, :100, 39] = 1
        result = paired_source_results(plan, before, after)
        self.assertEqual(result['occurrences_losing_presence'], 1)
        self.assertEqual(result['occurrences_losing_longest'], 1)
        self.assertFalse(result['no_occurrence_loss'])
        self.assertGreater(result['by_source']['a']['adapted_present'],
                           result['by_source']['a']['baseline_present'])

    def test_frame_gate_includes_false_silence_and_each_chord_size(self):
        truth = np.zeros((4, 172, 88), bool)
        for i, size in enumerate((3, 4, 5), 1):
            truth[i, :, :size] = True
        perfect = truth.astype(np.float32)
        self.assertTrue(representation_gate(frame_summary(perfect, truth), 99))
        false = perfect.copy(); false[0, 0, 80] = 1
        summary = frame_summary(false, truth)
        self.assertEqual(summary['silence_extra_note_frames'], 1)
        self.assertFalse(representation_gate(summary, 99))
        missing = perfect.copy(); missing[3] = 0
        self.assertFalse(representation_gate(frame_summary(missing, truth), 99))

    def test_frozen_spec_and_remote_guard(self):
        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root/'docs/recovery/basic-pitch-adaptation-20261122.json').read_text())
        self.assertEqual(spec['settings'], SETTINGS)
        self.assertEqual(spec['streaming'], STREAMING)
        from tools.portable_basic_pitch_adaptation import run
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaises(RuntimeError):
                run(Path('must-not-read'), Path('must-not-create'))


if __name__ == '__main__':
    unittest.main()
