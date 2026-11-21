"""Synthetic causal and scoring checks; no recorded arrays, audio or model."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_basic_pitch_streaming import activation
from tests.test_midi_lifecycle_analysis import label
from tools.basic_pitch_cached_diagnosis import decode_cached
from tools.basic_pitch_onset_decoder import (OnsetConfirmedDecoder, candidate_measurements,
    clock_events, decode_onset_cached, onset_screen)
from tools.pitch_detector_comparison import score


def decode(pairs):
    return decode_onset_cached([p[0] for p in pairs], [p[1] for p in pairs])


class OnsetDecoderTests(unittest.TestCase):
    def test_persistence_without_onset_is_the_removed_start_path(self):
        pairs = [activation(value=.9) for _ in range(12)]
        self.assertEqual(decode(pairs), ([], []))
        reference, opened = decode_cached([p[0] for p in pairs], [p[1] for p in pairs])
        self.assertEqual(reference, [dict(kind='on', note=60, frame=2)])
        self.assertEqual(opened, [60])

    def test_preceding_onset_is_remembered_but_start_is_never_backdated(self):
        pairs = [activation(onset=.5), activation(), activation(value=.3)]
        self.assertEqual(decode(pairs), ([dict(kind='on', note=60, frame=2)], [60]))
        expired = pairs[:2] + [activation(), activation(value=1.)]
        self.assertEqual(decode(expired), ([], []))

    def test_onset_needs_frame_evidence_and_tokens_are_single_use(self):
        pairs = [activation(onset=.9), activation(value=.5)] + [activation()]*3
        pairs += [activation(value=.8)]*5
        self.assertEqual(decode(pairs), ([dict(kind='on', note=60, frame=1),
            dict(kind='off', note=60, frame=4)], []))

    def test_active_onsets_cannot_retrigger_or_license_a_later_start(self):
        pairs = [activation(value=.4, onset=.9)]
        pairs += [activation(onset=.9) for _ in range(3)]
        pairs += [activation(value=.8)]*4 + [activation(value=.8, onset=.5)]
        self.assertEqual(decode(pairs), ([dict(kind='on', note=60, frame=0),
            dict(kind='off', note=60, frame=3), dict(kind='on', note=60, frame=8)], [60]))

    def test_release_hysteresis_resets_and_pitches_remain_independent(self):
        pairs = [activation(value=.5, onset=.8), activation(), activation(),
                 activation(value=.4), activation(), activation(), activation()]
        pairs[4][0][72-21] = .7
        pairs[4][1][72-21] = .8
        events, opened = decode(pairs)
        self.assertEqual(events, [dict(kind='on', note=60, frame=0),
            dict(kind='on', note=72, frame=4), dict(kind='off', note=60, frame=6)])
        self.assertEqual(opened, [72])

    def test_future_outputs_do_not_change_a_prefix(self):
        prefix = [activation(onset=.8), activation(value=.4), activation()]
        a = decode(prefix + [activation(value=.8, onset=.9)]*10)[0]
        b = decode(prefix + [activation()]*10)[0]
        expected = decode(prefix)[0]
        self.assertEqual([e for e in a if e['frame'] < len(prefix)], expected)
        self.assertEqual([e for e in b if e['frame'] < len(prefix)], expected)

    def test_invalid_data_is_not_converted_to_silence(self):
        for value in (float('nan'), float('inf'), -.1, 1.1):
            with self.assertRaises(ValueError):
                OnsetConfirmedDecoder().consume(*activation(value=value), 0)
        with self.assertRaises(ValueError):
            OnsetConfirmedDecoder().consume(*activation(), 1)
        with self.assertRaises(ValueError):
            decode_onset_cached([[0.]*88], [])

    def test_cached_clock_uses_source_completion_not_nominal_frame(self):
        frames = [[0,0,1860,8320], [1,256,1860,8320], [2,512,2372,10880]]
        timing = [[8320,86_666_667,10,96_666_667,0,0,0,0,1],
                  [10880,113_333_334,10,123_333_334,0,0,0,0,1]]
        events = [dict(kind='on',note=60,frame=1), dict(kind='off',note=60,frame=2)]
        clocked = clock_events(events,frames,timing)
        self.assertEqual([e['emitted_ns'] for e in clocked], [96_666_667,123_333_334])
        self.assertEqual([e['available_ns'] for e in clocked], [86_666_667,113_333_334])
        self.assertNotIn('emitted_ns', events[0])
        with self.assertRaises(ValueError):
            clock_events(events,frames,timing+[timing[0]])

    def test_coverage_loss_is_reported_even_when_false_notes_fall(self):
        clock = dict(sample_count=9600, sample_rate=96000)
        labels = [label(0,960,8640)]
        reference = score([(960,8640,60),(960,8640,72)],labels,**clock)
        events = [dict(kind='on',note=60,frame=0,available_ns=20_000_000,emitted_ns=20_000_000),
                  dict(kind='off',note=60,frame=1,available_ns=80_000_000,emitted_ns=80_000_000)]
        result = candidate_measurements(events,
            dict(measurement=reference,zero_compute_measurement=reference),reference,labels,clock)
        comparison = result['saved_fifo']['comparison_to_causal_reference']
        self.assertEqual(comparison['sample_deltas']['extra_pitch_voice_samples'], -7680)
        self.assertEqual(comparison['label_deltas'][0]['present_samples_delta'], -1920)
        self.assertFalse(comparison['no_pitch_safety_regression'])
        screen = onset_screen({k:dict(candidate=result) for k in ('ordinary','extended-middle')})
        self.assertFalse(screen['incremental_screen_pass'])
        self.assertFalse(screen['strict_replacement_screen_pass'])

    def test_remote_guard_precedes_recorded_cache_or_output_access(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'absent-output'
            result = subprocess.run([sys.executable,'-m','tools.portable_basic_pitch_onset_decoder',
                '--spec','absent','--output',str(output)],capture_output=True,text=True,
                env={k:v for k,v in os.environ.items() if k!='GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode,0)
            self.assertIn('requires GitHub Actions',result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
