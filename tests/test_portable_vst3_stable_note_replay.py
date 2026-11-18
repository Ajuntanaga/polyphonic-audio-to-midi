"""Saved callback and transfer accounting contracts; native work stays on GHA."""
import copy
import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import portable_vst3_stable_note_replay as runner
from tools.portable_vst3_corpus_replay import assess
from tools.portable_vst3_recovery_replay import assess as assess_recovery
from tests import test_portable_vst3_corpus_replay as corpus_tests
from tests import test_portable_vst3_recovery_replay as recovery_tests


class StableNoteComponentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.raw = ("# m3_ledger_callbacks_v1\n" + '\t'.join(runner.CALLBACK_FIELDS) + '\n'
                    '1\tsource\ton\t60\t127\t0\t1\t0\n'
                    '599\tsource\toff\t60\t0\t0\t1\t3\n').encode()
        compressed = gzip.compress(self.raw, mtime=0)
        self.reference = dict(recording_clock=dict(sample_count=600, sample_rate=96000), runs={})
        self.archive = self.root / 'saved.zip'
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for mode in runner.MODES:
                name = mode + '-callbacks.tsv.gz'
                archive.writestr('nested/' + name, compressed)
                self.reference['runs'][mode] = dict(callbacks=dict(file=name,
                    bytes=len(compressed), sha256=hashlib.sha256(compressed).hexdigest(),
                    raw_bytes=len(self.raw), raw_sha256=hashlib.sha256(self.raw).hexdigest(),
                    captured_raw_bytes=len(self.raw), captured_raw_sha256=hashlib.sha256(self.raw).hexdigest(),
                    captured_rows=2, retained_rows=2, discarded_rows=0,
                    start_sample_inclusive=0, end_sample_exclusive=600))
            archive.writestr('unused.bin', b'not staged')
        self.reference['artifact'] = dict(size_in_bytes=self.archive.stat().st_size,
            sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def test_complete_frozen_callbacks_loaded_without_bulk_extraction(self):
        events = runner.stage_references(self.reference, self.archive, self.root / 'stage')
        self.assertEqual(set(events), set(runner.MODES))
        self.assertEqual(events['stable_note'][1]['source_sequence'], 3)
        self.assertEqual(events['stable_note'][1]['sequence'], 1)
        self.assertEqual(len(list((self.root / 'stage').iterdir())), 2)
        callbacks = [dict(event, velocity=1.0 if event['kind'] == 'on' else 0.0)
                     for event in events['stable_note']]
        self.assertTrue(runner.compare_callbacks(callbacks, events['stable_note'])['exact_saved_midi_match'])
        # Same pitch at the wrong sink or a swallowed real release must fail.
        callbacks[1]['voice_id'] = 1
        self.assertFalse(runner.compare_callbacks(callbacks, events['stable_note'])['exact_saved_midi_match'])
        self.assertFalse(runner.compare_callbacks(callbacks[:1], events['stable_note'])['exact_saved_midi_match'])

    def test_partial_or_substituted_trace_cannot_certify_parity(self):
        for index, change in enumerate(({'discarded_rows': 1}, {'captured_rows': 3},
                {'end_sample_exclusive': 599}, {'sha256': '0' * 64},
                {'raw_bytes': runner.MAX_TRACE_BYTES + 1}, {'file': 'missing'})):
            reference = copy.deepcopy(self.reference)
            reference['runs']['stable_note']['callbacks'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.stage_references(reference, self.archive, self.root / str(index))
        reference = copy.deepcopy(self.reference)
        reference['artifact']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            runner.stage_references(reference, self.archive, self.root / 'bad')

    def test_duplicate_named_trace_is_rejected(self):
        with zipfile.ZipFile(self.archive, 'a') as archive:
            archive.writestr('other/stable_note-callbacks.tsv.gz', gzip.compress(self.raw, mtime=0))
        self.reference['artifact'] = dict(size_in_bytes=self.archive.stat().st_size,
            sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            runner.stage_references(self.reference, self.archive, self.root / 'duplicate')

    def test_source_bundle_and_actual_inputs_match_frozen_reference(self):
        source = dict(commit='a' * 40, input_release='fixture',
            input_bundle_sha256='b' * 64, original_input_manifest_sha256='c' * 64)
        files = {}
        for name in ('ordinary.wav', 'ordinary.tsv', 'calibration.m3cb'):
            (self.root / name).write_bytes(name.encode())
            files[name] = dict(sha256=hashlib.sha256(name.encode()).hexdigest())
        manifest = dict(source=source, files=files)
        self.reference.update(schema='m3_vst3_stable_note_identity_references_v1',
            state='completed', final=True, dataset='ordinary', settings=runner.SETTINGS,
            source=source.copy(), inputs=copy.deepcopy(files))
        verified, _ = runner.verify_inputs(self.root, manifest, self.reference, source['commit'])
        self.assertEqual(set(verified), set(files))
        self.reference['inputs']['ordinary.wav']['sha256'] = 'd' * 64
        with self.assertRaisesRegex(ValueError, 'Input hash'):
            runner.verify_inputs(self.root, manifest, self.reference, source['commit'])

    def test_accepting_transfer_accounting_is_explicit_and_cannot_hide_missing_events(self):
        fixture = corpus_tests.Vst3CorpusReplayTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        native = dict(fixture.native, stable_note_identity=True, transferred_pairs=1,
                      detector_transitions=5)
        callbacks = fixture.callbacks()
        result = assess(native, callbacks, clock=fixture.clock, sample_bits=32, trial=True,
                        stable_note_identity=True)
        self.assertTrue(result['gate_pass'])
        native['detector_transitions'] = 6
        self.assertFalse(assess(native, callbacks, clock=fixture.clock, sample_bits=32, trial=True,
                               stable_note_identity=True)['gate_pass'])
        with self.assertRaisesRegex(ValueError, 'identity or transfer'):
            assess(native, callbacks, clock=fixture.clock, sample_bits=32, trial=True)
        native['transferred_pairs'] = True
        with self.assertRaises(ValueError):
            assess(native, callbacks, clock=fixture.clock, sample_bits=32, trial=True,
                   stable_note_identity=True)

    def test_recovery_accounts_for_transfers_but_never_during_cleanup_or_hold(self):
        fixture = recovery_tests.Vst3RecoveryReplayTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        _, callbacks = fixture.check()
        native = copy.deepcopy(fixture.native)
        native['stable_note_identity'] = True
        for boundary in native['boundaries']:
            boundary['transferred_pairs'] = 0
        native['boundaries'][-1].update(transferred_pairs=1, detector_transitions=5)
        result = assess_recovery(native, callbacks, clock=fixture.clock, sample_bits=32,
                                 stable_note_identity=True)
        self.assertTrue(result['gate_pass'])
        self.assertEqual(result['post_recovery_transferred_pairs'], 1)
        for boundary in native['boundaries'][1:4]:
            boundary['transferred_pairs'] = 1
        result = assess_recovery(native, callbacks, clock=fixture.clock, sample_bits=32,
                                 stable_note_identity=True)
        self.assertFalse(result['gates']['no_transfers_while_recovering'])
        self.assertFalse(result['gate_pass'])


if __name__ == '__main__':
    unittest.main()
