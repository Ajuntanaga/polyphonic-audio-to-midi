"""Synthetic mechanics and acceptance checks; no ONNX, model or recordings."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from tests.test_basic_pitch_bass_view import FakeBackend
from tools.basic_pitch_recent_normalization import assess, stream_pair
from tools.basic_pitch_streaming import stream_blocks


class RecentNormalizationTests(unittest.TestCase):
    def test_same_inputs_frames_events_and_shared_fifo(self):
        source = np.random.default_rng(8).normal(0, .1, 32005).astype(np.float32)
        reference, candidate, original = FakeBackend(), FakeBackend(), FakeBackend(full=True)
        blocks = lambda: (source[i:i+640] for i in range(0, len(source), 640))
        calls = [0]
        def clock():
            calls[0] += 100000
            return calls[0]
        result = stream_pair(blocks(), len(source), reference, candidate, clock_ns=clock)
        saved = stream_blocks(blocks(), original)
        self.assertEqual(result['reference']['frames'], saved['frames'])
        self.assertEqual(result['reference']['events'], result['candidate']['events'])
        for a, b, c in zip(reference.windows, candidate.windows, original.windows):
            np.testing.assert_array_equal(a, b)
            np.testing.assert_array_equal(a, c)
        self.assertEqual(len(reference.windows), len(original.windows))
        self.assertEqual(len(candidate.windows), len(original.windows))
        stable = lambda rows: [{k: e[k] for k in ('kind', 'note', 'frame', 'available_ns')} for e in rows]
        self.assertEqual(stable(saved['events']), stable(result['reference']['events']))
        timing = {row[0]: row for row in result['timing']}
        frames = {row[0]: row for row in result['reference']['frames']}
        for event in result['reference']['events']:
            row = timing[frames[event['frame']][3]]
            self.assertEqual((event['available_ns'], event['emitted_ns']), (row[1], row[3]))
            self.assertGreater(event['emitted_ns'], event['available_ns'])
        self.assertEqual(result['source_samples'], len(source))

    def test_models_do_not_share_decoder_state_and_incomplete_source_fails(self):
        source = np.zeros(18001, dtype=np.float32)
        result = stream_pair((source[i:i+640] for i in range(0, len(source), 640)), len(source),
                             FakeBackend(pitches=(40,)), FakeBackend(pitches=(72,)))
        self.assertEqual(result['reference']['open_decoder_pitches'], [40])
        self.assertEqual(result['candidate']['open_decoder_pitches'], [72])
        with self.assertRaises(ValueError):
            stream_pair([np.zeros(640)], 1280, FakeBackend(), FakeBackend())
        with self.assertRaises(ValueError):
            stream_pair([np.zeros(639), np.zeros(640)], 1279, FakeBackend(), FakeBackend())

    def test_quality_gate_requires_both_recordings_and_per_label_safety(self):
        from tests.test_midi_lifecycle_analysis import label
        from tools.pitch_detector_comparison import score, compare
        labels = [label(0, 20, 120, note=40), label(1, 20, 120, note=64)]
        base = [(20, 120, 64)]
        def dataset(spans):
            delta = compare(score(base, labels, sample_count=200, sample_rate=1000),
                            score(spans, labels, sample_count=200, sample_rate=1000))
            return dict(arms=dict(candidate=dict(serviced=dict(
                comparison_to_reference=delta, comparison_to_current=delta))))
        improved = dataset(base + [(20, 120, 40)])
        self.assertTrue(assess({'ordinary': improved, 'extended-middle': improved})['incremental_screen_pass'])
        for unsafe in (base+[(20, 120, 40), (140, 150, 40)], [(20, 120, 40), (21, 120, 64)]):
            self.assertFalse(assess({'ordinary': improved, 'extended-middle': dataset(unsafe)})['incremental_screen_pass'])
        with self.assertRaises(ValueError):
            assess({'ordinary': improved})

    def test_remote_guard_precedes_model_recordings_and_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_basic_pitch_recent_normalization',
                '--spec', 'absent', '--inputs', 'absent', '--model-checkout', 'absent', '--output', str(output)],
                capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__': unittest.main()
