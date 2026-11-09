"""Small input/accounting contracts; the actual VST3 replay runs on GitHub."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.portable_vst3_corpus_replay import SETTINGS, assess, read_callbacks, verify_inputs


HEADER = '# m3_vst3_corpus_events_v1\nsample\tkind\tnote\tvelocity\tnote_id\tchannel\n'


class Vst3CorpusReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'callbacks.tsv'
        self.rows = [(1, 'on', 60, .75, -1060, 0),
                     (513, 'off', 60, 0, -1060, 0),
                     (599, 'on', 60, .5, -1188, 1)]
        self.clock = dict(sample_count=600, sample_rate=96000)
        self.native = dict(schema='m3_vst3_corpus_native_v1', routing='per_voice',
            sample_bits=32, block_samples=512, trial=True, **self.clock,
            processed_samples=600, blocks=2, detector_samples=600,
            detector_transitions=3, queue_rejections=0, event_add_attempts=3,
            accepted_events=3, output_blocked_blocks=0, dry_audio_mismatches=0,
            process_failures=0, output_blocked_at_eof=False,
            calibration_merge_matches=True, invalid_event=False,
            trace_write_failed=False, first_blocked_sample=None)

    def callbacks(self, rows=None, expected_count=3):
        self.path.write_text(HEADER + ''.join('\t'.join(map(str, row)) + '\n'
                                             for row in (self.rows if rows is None else rows)))
        return read_callbacks(self.path, sample_count=600, expected_count=expected_count)

    def check(self, native=None, callbacks=None):
        return assess(self.native if native is None else native,
                      self.callbacks() if callbacks is None else callbacks,
                      clock=self.clock, sample_bits=32, trial=True)

    def test_complete_detection_and_legal_callbacks_pass_with_eof_open_retained(self):
        callbacks = self.callbacks()
        self.assertTrue(self.check(callbacks=callbacks)['gate_pass'])
        self.assertEqual(callbacks['note_ons_open_at_eof'][0]['channel'], 1)
        self.assertEqual(callbacks['note_ons_open_at_eof'][0]['note_id'], -1188)
        self.assertEqual(callbacks['observed_events'], 3)

    def test_bad_identity_velocity_clock_and_truncated_capture_are_rejected(self):
        for index, value in ((0, 600), (1, 'pitchbend'), (2, 128), (3, float('nan')),
                             (3, 0), (4, -1188), (5, 8)):
            with self.subTest(index=index, value=value):
                rows = copy.deepcopy(self.rows)
                row = list(rows[0])
                row[index] = value
                rows[0] = row
                with self.assertRaises(ValueError):
                    self.callbacks(rows)
        with self.assertRaises(ValueError):
            self.callbacks(self.rows[::-1])
        with self.assertRaisesRegex(ValueError, 'count differs'):
            self.callbacks(self.rows[:2])

    def test_same_pitch_unisons_are_separate_but_cross_pitch_same_channel_fails(self):
        rows = [(1, 'on', 60, .75, -1060, 0), (1, 'on', 60, .5, -1188, 1),
                (599, 'off', 60, 0, -1060, 0)]
        self.assertTrue(self.check(callbacks=self.callbacks(rows))['gate_pass'])
        rows[1] = (2, 'on', 62, .5, -1062, 0)
        assessment = self.check(callbacks=self.callbacks(rows))
        self.assertFalse(assessment['gate_pass'])
        self.assertFalse(assessment['gates']['legal_callback_ownership'])

    def test_output_fault_cannot_pass_on_full_audio_passthrough(self):
        native = dict(self.native, detector_samples=514, output_blocked_blocks=1,
                      output_blocked_at_eof=True, first_blocked_sample=512,
                      queue_rejections=1)
        assessment = self.check(native)
        self.assertTrue(assessment['gates']['full_audio_processed'])
        self.assertFalse(assessment['gates']['full_detector_coverage'])
        self.assertFalse(assessment['gates']['no_output_faults'])
        self.assertEqual(assessment['samples_not_analyzed'], 86)
        self.assertFalse(assessment['gate_pass'])

    def test_missing_mistyped_or_contradictory_native_accounting_is_rejected(self):
        changes = ({'detector_samples': None}, {'accepted_events': True},
                   {'calibration_merge_matches': 1}, {'sample_count': 599},
                   {'sample_bits': 64}, {'trial': False}, {'blocks': 1},
                   {'detector_samples': 601}, {'accepted_events': 2},
                   {'event_add_attempts': 2}, {'first_blocked_sample': 512},
                   {'output_blocked_blocks': 1, 'first_blocked_sample': 513})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check(dict(self.native, **change))

    def test_reference_recording_hash_and_bundle_are_required(self):
        source_sha = 'a' * 40
        source = dict(commit=source_sha, input_release='fixture',
                      input_bundle_sha256='b' * 64, original_input_manifest_sha256='c' * 64)
        files = {}
        for name in ('ordinary.wav', 'calibration.m3cb'):
            data = name.encode()
            (self.root / name).write_bytes(data)
            files[name] = dict(sha256=hashlib.sha256(data).hexdigest())
        manifest = dict(source=source, files=files)
        reference = dict(state='completed', final=True, dataset='ordinary',
                         settings=SETTINGS, source=source,
                         runs={'reference-off': self.clock})
        verified, clock = verify_inputs(self.root, manifest, reference, source_sha)
        self.assertEqual(set(verified), set(files))
        self.assertEqual(clock, self.clock)
        changed = copy.deepcopy(manifest)
        changed['source']['input_bundle_sha256'] = 'd' * 64
        with self.assertRaisesRegex(ValueError, 'bundle provenance differs'):
            verify_inputs(self.root, changed, reference, source_sha)
        (self.root / 'ordinary.wav').write_bytes(b'other recording')
        with self.assertRaisesRegex(ValueError, 'Input hash differs'):
            verify_inputs(self.root, manifest, reference, source_sha)


if __name__ == '__main__':
    unittest.main()
