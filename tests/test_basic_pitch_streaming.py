"""Causal clock, synthetic FIR and decoder checks; no recorded audio or model."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.basic_pitch_streaming import (CausalResampler, FIRST_END, FifoClock,
    ForwardDecoder, emission_spans, stream_blocks, timing_summary)


def activation(note=60, value=0., onset=0.):
    notes, onsets = [0.]*88, [0.]*88
    notes[note-21], onsets[note-21] = value, onset
    return notes, onsets


class CausalTests(unittest.TestCase):
    def test_attack_release_hysteresis_and_no_retrospective_filter(self):
        decoder = ForwardDecoder()
        self.assertEqual(decoder.consume(*activation(value=.3), 0), [])
        self.assertEqual(decoder.consume(*activation(value=.3), 1), [])
        self.assertEqual(decoder.consume(*activation(value=.3), 2),
                         [dict(kind='on', note=60, frame=2)])
        self.assertEqual(decoder.consume(*activation(value=.4, onset=.9), 3), [])
        self.assertEqual(decoder.consume(*activation(), 4), [])
        self.assertEqual(decoder.consume(*activation(), 5), [])
        self.assertEqual(decoder.consume(*activation(), 6),
                         [dict(kind='off', note=60, frame=6)])
        # Immediate onset needs frame evidence too; no retrospective deletion.
        self.assertEqual(decoder.consume(*activation(onset=.9), 7), [])
        self.assertEqual(decoder.consume(*activation(value=.3, onset=.5), 8),
                         [dict(kind='on', note=60, frame=8)])

    def test_intermittent_evidence_resets_attack_and_release(self):
        decoder = ForwardDecoder()
        for frame, value in enumerate([.5, .5, 0, .5, .5]):
            self.assertEqual(decoder.consume(*activation(value=value), frame), [])
        self.assertEqual(decoder.consume(*activation(value=.5), 5)[0]['kind'], 'on')
        for frame, value in enumerate([0, 0, .5, 0, 0], 6):
            self.assertEqual(decoder.consume(*activation(value=value), frame), [])
        self.assertEqual(decoder.consume(*activation(), 11)[0]['kind'], 'off')

    def test_invalid_frame_or_activation_is_not_silence(self):
        with self.assertRaises(ValueError):
            ForwardDecoder().consume(*activation(), 1)
        with self.assertRaises(ValueError):
            ForwardDecoder().consume(*activation(value=float('nan')), 0)

    def test_fifo_retains_backlog_and_never_backdates(self):
        fifo = FifoClock()
        a, f, q = fifo.submit(640, 30_000_000)
        self.assertEqual((a, f, q), (6_666_667, 36_666_667, 0))
        a, f, q = fifo.submit(1280, 30_000_000)
        self.assertEqual((a, f, q), (13_333_334, 66_666_667, 23_333_333))
        events = [dict(kind='on', note=60, available_ns=10_000_000, emitted_ns=80_000_000),
                  dict(kind='off', note=60, available_ns=20_000_000, emitted_ns=100_000_000),
                  dict(kind='on', note=72, available_ns=25_000_000, emitted_ns=120_000_000)]
        spans, audit = emission_spans(events, 'emitted_ns', 9600)
        self.assertEqual(spans, [(7680, 9600, 60)])
        self.assertEqual(audit['events_at_or_after_eof'], 2)
        self.assertEqual(audit['pitches_active_at_recording_end'], [60])
        ideal, _ = emission_spans(events, 'available_ns', 9600)
        self.assertEqual(ideal, [(960,1920,60), (2400,9600,72)])
        with self.assertRaises(ValueError):
            emission_spans(events, 'frame', 9600)

    def test_causal_resampler_matches_fir_prefix_and_partial_eof(self):
        import numpy as np
        from scipy.signal import upfirdn
        source = np.random.default_rng(7).normal(0,.1,32005).astype(np.float32)
        resampler = CausalResampler()
        pieces = [resampler.consume(source[i:i+640]) for i in range(0,len(source),640)]
        output = np.concatenate(pieces)
        direct = upfirdn(resampler.h, source, up=147, down=640)[:len(output)]
        np.testing.assert_allclose(output, direct, atol=1e-7, rtol=1e-6)
        self.assertEqual(len(pieces[-1]), 2)  # five source samples, no right extension
        changed = source.copy()
        changed[640:] += 100
        prefix = CausalResampler().consume(changed[:640])
        np.testing.assert_array_equal(prefix, output[:147])
        with self.assertRaises(ValueError):
            resampler.consume(source[:640])

    def test_windows_use_only_arrived_samples_and_unique_frames(self):
        import numpy as np
        from scipy.signal import upfirdn
        source = np.random.default_rng(8).normal(0,.1,32005).astype(np.float32)

        class FakeBackend:
            def __init__(self):
                self.windows = []

            def predict(self, window):
                self.windows.append(window.copy())
                notes, onsets = np.zeros((172,88)), np.zeros((172,88))
                notes[164:166,39] = .4
                return notes, onsets

        backend = FakeBackend()
        result = stream_blocks((source[i:i+640] for i in range(0,len(source),640)), backend)
        direct = upfirdn(CausalResampler().h, source, up=147, down=640)
        for k, window in enumerate(backend.windows):
            end = FIRST_END + 512*k
            expected = np.pad(direct[max(0,end-43844):end], (max(0,43844-end),0))
            np.testing.assert_allclose(window, expected, atol=1e-7, rtol=1e-6)
        self.assertEqual([r[0] for r in result['frames']], list(range(len(result['frames']))))
        for frame, nominal, end, source_end in result['frames']:
            self.assertLess((end-1)*96000, source_end*22050)
            self.assertIn(end-nominal, (1860,1604))
        self.assertEqual(len(result['events']), 1)
        event = result['events'][0]
        self.assertEqual(event['frame'], 2)
        self.assertGreaterEqual(event['emitted_ns'], event['available_ns'])
        self.assertEqual(result['open_decoder_pitches'], [60])
        self.assertEqual(result['notes'].shape[0], result['model_calls']*2)
        self.assertEqual(timing_summary(result['timing'])['model_call_ns']['count'], result['model_calls'])

    def test_driver_guard_precedes_input_and_model_access(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'absent-output'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_basic_pitch_streaming',
                '--spec', 'absent', '--inputs', 'absent', '--model-checkout', 'absent',
                '--output', str(output)], capture_output=True, text=True,
                env={k:v for k,v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())

    def test_readout_only_contract_preserves_frames_events_and_input(self):
        import numpy as np
        source = np.arange(32000, dtype=np.float32)/64000

        class Backend:
            def __init__(self, start):
                self.output_frame_start = start
                self.windows = []

            def predict(self, window):
                self.windows.append(window.copy())
                values = np.zeros((172,88), dtype=np.float32)
                values[164:166,39] = .7
                return ((values, values.copy()) if self.output_frame_start == 0
                        else (values[164:166], values[164:166].copy()))

        results, backends = [], []
        for start in (0,164):
            backend = Backend(start)
            clock = iter(range(0,10000))
            results.append(stream_blocks((source[i:i+640] for i in range(0,len(source),640)),
                                         backend, clock_ns=lambda: next(clock)))
            backends.append(backend)
        self.assertGreater(results[0]['model_calls'], 0)
        self.assertEqual(len(results[0]['events']), 1)
        for key in ('events','frames','timing','open_decoder_pitches','model_calls'):
            self.assertEqual(results[0][key], results[1][key])
        for key in ('notes','onsets'):
            np.testing.assert_array_equal(results[0][key], results[1][key])
        np.testing.assert_array_equal(backends[0].windows, backends[1].windows)
        with self.assertRaisesRegex(ValueError, 'earlier frame'):
            stream_blocks(iter(()), Backend(164), additional_readout_start=160)
        with self.assertRaisesRegex(ValueError, 'frame origin'):
            stream_blocks(iter(()), Backend(162))
        wrong = Backend(164)
        wrong.predict = Backend(0).predict
        with self.assertRaisesRegex(ValueError, 'output shape'):
            stream_blocks((source[i:i+640] for i in range(0,len(source),640)), wrong)


if __name__ == '__main__':
    unittest.main()
