"""Saved-event comparison contracts; actual component execution stays on GitHub."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from tools import portable_vst3_completion_midi_replay as runner


RAW_HEADER = '# m3_midi_events_v1\nsample\tkind\tnote\tvelocity\tvoice_id\tsequence\n'
CALLBACK_HEADER = '# m3_vst3_corpus_events_v1\nsample\tkind\tnote\tvelocity\tnote_id\tchannel\n'
SOURCE = 'a' * 40


class CompletionMidiComponentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # A different lane attacks before the earlier lane releases at sample 2.
        # The component ledger may reorder those two events, preserving both.
        self.events = [
            dict(sample=1, kind='on', note=60, velocity=127, voice_id=0, sequence=0),
            dict(sample=2, kind='on', note=62, velocity=64, voice_id=1, sequence=1),
            dict(sample=2, kind='off', note=60, velocity=0, voice_id=0, sequence=2),
            dict(sample=3, kind='off', note=62, velocity=0, voice_id=1, sequence=3),
        ]
        self.clock = dict(sample_count=600, sample_rate=96000)
        self.manifest = dict(source=dict(commit=SOURCE, input_release='fixture',
            input_bundle_sha256='b' * 64, original_input_manifest_sha256='c' * 64), files={})
        for name in ('physical-long.wav', 'calibration.m3cb'):
            data = name.encode()
            (self.root / name).write_bytes(data)
            self.manifest['files'][name] = dict(sha256=hashlib.sha256(data).hexdigest())
        self.reference = dict(schema='m3_vst3_completion_midi_references_v1',
            state='completed', final=True, dataset='physical-long', settings=runner.SETTINGS,
            source=dict(self.manifest['source'], commit='d' * 40),
            recording_clock=self.clock, runs={})
        self.archive = self.root / 'saved.zip'
        raw = RAW_HEADER + ''.join('\t'.join(str(event[key]) for key in
            ('sample', 'kind', 'note', 'velocity', 'voice_id', 'sequence')) + '\n'
            for event in self.events)
        self.raw = raw.encode()
        compressed = gzip.compress(self.raw, mtime=0)
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for mode in runner.MODES:
                name = mode + '-midi.tsv.gz'
                archive.writestr('nested/' + name, compressed)
                self.reference['runs'][mode] = dict(file=name,
                    bytes=len(compressed), sha256=hashlib.sha256(compressed).hexdigest(),
                    raw_bytes=len(self.raw), raw_sha256=hashlib.sha256(self.raw).hexdigest(),
                    captured_raw_bytes=len(self.raw),
                    captured_raw_sha256=hashlib.sha256(self.raw).hexdigest(),
                    captured_rows=4, retained_rows=4, discarded_rows=0,
                    start_sample_inclusive=0, end_sample_exclusive=600)
        self.update_archive_identity()

    def update_archive_identity(self):
        self.reference['artifact'] = dict(size_in_bytes=self.archive.stat().st_size,
            sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def callbacks(self):
        result = []
        for index in (0, 2, 1, 3):
            event = dict(self.events[index])
            velocity = struct.unpack('f', struct.pack('f', event['velocity'] / 127))[0]
            event['velocity'] = float(format(velocity, '.9g'))
            result.append(event)
        return result

    def test_ledger_reordering_and_float32_velocity_preserve_saved_midi(self):
        result = runner.compare_callbacks(self.callbacks(), self.events)
        self.assertTrue(result['exact_saved_midi_match'])
        self.assertEqual(result['expected_events'], 4)
        unsorted = [self.callbacks()[index] for index in (0, 2, 1, 3)]
        self.assertFalse(runner.compare_callbacks(unsorted, self.events)['exact_saved_midi_match'])

    def test_missing_extra_shifted_or_altered_callback_cannot_pass(self):
        for field, value in (('sample', 0), ('kind', 'off'), ('note', 61),
                             ('voice_id', 1), ('velocity', .99)):
            with self.subTest(field=field):
                callbacks = self.callbacks()
                callbacks[0][field] = value
                self.assertFalse(runner.compare_callbacks(callbacks, self.events)['exact_saved_midi_match'])
        for callbacks in (self.callbacks()[:-1], self.callbacks() + self.callbacks()[-1:]):
            self.assertEqual(runner.compare_callbacks(callbacks, self.events)['differing_events'], 1)

    def test_complete_saved_traces_are_loaded_without_extracting_other_members(self):
        with zipfile.ZipFile(self.archive, 'a') as archive:
            archive.writestr('unrelated.bin', b'not needed')
        self.update_archive_identity()
        destination = self.root / 'references'
        loaded = runner.stage_references(self.reference, self.archive, destination)
        self.assertEqual(loaded, dict.fromkeys(runner.MODES, self.events))
        self.assertEqual(sorted(path.name for path in destination.iterdir()),
                         sorted(mode + '.tsv' for mode in runner.MODES))

    def test_substituted_partial_or_oversized_reference_is_rejected(self):
        changes = ({'discarded_rows': 1}, {'captured_rows': 5},
            {'end_sample_exclusive': 599}, {'start_sample_inclusive': 1},
            {'raw_bytes': runner.MAX_TRACE_BYTES + 1},
            {'sha256': '0' * 64}, {'raw_sha256': '0' * 64, 'captured_raw_sha256': '0' * 64},
            {'file': 'missing.tsv.gz'})
        for index, change in enumerate(changes):
            with self.subTest(change=change):
                reference = copy.deepcopy(self.reference)
                reference['runs'][runner.MODES[0]].update(change)
                with self.assertRaises(ValueError):
                    runner.stage_references(reference, self.archive, self.root / str(index))
        reference = copy.deepcopy(self.reference)
        reference['artifact']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'artifact size or SHA-256'):
            runner.stage_references(reference, self.archive, self.root / 'bad-archive')

    def test_duplicate_named_member_is_rejected(self):
        name = self.reference['runs'][runner.MODES[0]]['file']
        with zipfile.ZipFile(self.archive, 'a') as archive:
            archive.writestr('other/' + name, gzip.compress(self.raw, mtime=0))
        self.update_archive_identity()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            runner.stage_references(self.reference, self.archive, self.root / 'duplicate')

    def test_input_source_bundle_and_clock_must_match_the_saved_recording(self):
        verified, clock = runner.verify_inputs(self.root, self.manifest, self.reference, SOURCE)
        self.assertEqual(set(verified), set(self.manifest['files']))
        self.assertEqual(clock, self.clock)
        for key in ('commit', 'input_bundle_sha256', 'original_input_manifest_sha256'):
            changed = copy.deepcopy(self.manifest)
            changed['source'][key] = 'e' * 64
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.verify_inputs(self.root, changed, self.reference, SOURCE)
        reference = copy.deepcopy(self.reference)
        reference['recording_clock']['sample_count'] = True
        with self.assertRaisesRegex(ValueError, 'recording clock'):
            runner.verify_inputs(self.root, self.manifest, reference, SOURCE)
        (self.root / 'physical-long.wav').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Input hash'):
            runner.verify_inputs(self.root, self.manifest, self.reference, SOURCE)

    def invoke(self, *, alter_callback=False, wrong_policy=False):
        manifest_path, reference_path = self.root / 'manifest.json', self.root / 'reference.json'
        manifest_path.write_text(json.dumps(self.manifest))
        reference_path.write_text(json.dumps(self.reference))
        binary = self.root / 'mock-native'
        binary.write_bytes(b'never executed')
        args = SimpleNamespace(binary=binary, corpus=self.root, manifest=manifest_path,
            reference=reference_path, evidence_archive=self.archive,
            source_sha=SOURCE, output=self.root / 'output')
        calls = []

        def native(command, *, stdout, stderr, timeout, check):
            calls.append(command)
            bits = int(command[command.index('--sample-bits') + 1])
            retention = command[command.index('--completion-midi-retention') + 1] == '1'
            path = Path(command[command.index('--events') + 1])
            callbacks = self.callbacks()
            if alter_callback:
                callbacks[0]['sample'] = 0  # Legal MIDI and full coverage, wrong timing.
            rows = [(event['sample'], event['kind'], event['note'], event['velocity'],
                     -1000 - event['voice_id'] * 128 - event['note'], event['voice_id'])
                    for event in callbacks]
            path.write_text(CALLBACK_HEADER + ''.join('\t'.join(map(str, row)) + '\n' for row in rows))
            native_report = dict(schema='m3_vst3_corpus_native_v1', routing='per_voice',
                sample_bits=bits, block_samples=512, trial=True, **self.clock,
                completion_midi_retention=not retention if wrong_policy else retention,
                processed_samples=600, blocks=2, detector_samples=600, detector_transitions=4,
                queue_rejections=0, event_add_attempts=4, accepted_events=4,
                output_blocked_blocks=0, dry_audio_mismatches=0, process_failures=0,
                output_blocked_at_eof=False, calibration_merge_matches=True,
                invalid_event=False, trace_write_failed=False, first_blocked_sample=None)
            stdout.write(json.dumps(native_report))
            return SimpleNamespace(returncode=0)

        with patch.object(runner.subprocess, 'check_output', return_value=SOURCE + '\n'), \
                patch.object(runner.subprocess, 'run', side_effect=native):
            result = runner.run(args)
        return result, calls

    def test_four_serialized_passes_compare_each_mode_and_preserve_evidence(self):
        result, calls = self.invoke()
        self.assertTrue(result['integration_gate_pass'])
        self.assertEqual(len(calls), 4)
        self.assertEqual([call[call.index('--completion-midi-retention') + 1] for call in calls],
                         ['0', '1', '0', '1'])
        self.assertTrue(all(result['format_callback_identity'].values()))
        self.assertFalse(result['promotion_accepted'])
        self.assertFalse(result['installed_output_changed'])
        for name, run in result['runs'].items():
            self.assertEqual(run['comparison']['observed_events'], 4)
            self.assertTrue((self.root / 'output' / run['trace']['file']).is_file())
            self.assertFalse((self.root / 'output' / name / 'callbacks.tsv').exists())

    def test_legal_but_shifted_callback_stops_before_later_passes(self):
        result, calls = self.invoke(alter_callback=True)
        self.assertEqual(len(calls), 1)
        self.assertTrue(result['final'])
        self.assertFalse(result['integration_gate_pass'])
        run = next(iter(result['runs'].values()))
        self.assertTrue(run['gates']['legal_callback_ownership'])
        self.assertFalse(run['gates']['exact_saved_midi_match'])

    def test_wrong_native_policy_is_recorded_as_error(self):
        with self.assertRaisesRegex(ValueError, 'retention policy differs'):
            self.invoke(wrong_policy=True)
        result = json.loads((self.root / 'output/report.json').read_text())
        self.assertEqual(result['state'], 'error')
        self.assertTrue(result['final'])


if __name__ == '__main__':
    unittest.main()
