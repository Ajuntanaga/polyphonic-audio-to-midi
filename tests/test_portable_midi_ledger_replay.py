"""Saved event provenance and production-ledger behavior; native cases run in CI."""
import copy
import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from tools.midi_lifecycle_analysis import read_events, raw_conflicts
from tools.portable_midi_ledger_replay import check_callbacks, stage_inputs


HEADER = '# m3_midi_events_v1\nsample\tkind\tnote\tvelocity\tvoice_id\tsequence\n'


def event_text(rows):
    return HEADER + ''.join('\t'.join(map(str, row)) + '\n' for row in rows)


class PureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.raw = event_text([(1, 'on', 60, 90, 0, 0), (70, 'off', 60, 0, 0, 1)])
        self.source_path = self.root / 'events.tsv'
        self.source_path.write_text(self.raw)
        events = read_events(self.source_path, sample_count=130, transition_count=2)
        self.source = dict(events=events, sample_count=130)
        conflicts = raw_conflicts(events)
        compressed = gzip.compress(self.raw.encode(), mtime=0)
        self.archive = self.root / 'evidence.zip'
        self.checkpoint = dict(schema='m3_spectral_lane_collision_trial_v1',
            state='completed', final=True, source=dict(run_id='123', run_attempt='1'), runs={})
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for mode in ('reference-off', 'trial-on'):
                archive.writestr(f'trial/{mode}/midi-event.tsv.gz', compressed)
                raw_sha = hashlib.sha256(self.raw.encode()).hexdigest()
                trace = dict(file='midi-event.tsv.gz', bytes=len(compressed),
                    sha256=hashlib.sha256(compressed).hexdigest(),
                    raw_bytes=len(self.raw), captured_raw_bytes=len(self.raw),
                    raw_sha256=raw_sha, captured_raw_sha256=raw_sha,
                    captured_rows=2, retained_rows=2, discarded_rows=0,
                    scope='complete recording', start_sample_inclusive=0,
                    end_sample_exclusive=130)
                self.checkpoint['runs'][mode] = dict(sample_count=130, sample_rate=96000,
                    traces={'midi-event': trace}, raw_midi_counts=conflicts['counts'],
                    raw_note_ons_open_at_eof=conflicts['raw_note_ons_open_at_eof'])
        self.checkpoint['artifacts'] = [dict(name='m3-evidence-123-1',
            sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())]

    def stage(self, checkpoint):
        return stage_inputs(checkpoint, self.archive, self.root)

    def test_complete_saved_streams_match_both_hash_layers_and_event_counts(self):
        inputs, artifact = self.stage(self.checkpoint)
        self.assertEqual(set(inputs), {'reference-off', 'trial-on'})
        self.assertEqual(artifact['name'], 'm3-evidence-123-1')
        for source in inputs.values():
            self.assertEqual(source['events'], self.source['events'])
            self.assertEqual(source['path'].read_text(), self.raw)

    def test_archive_or_capture_hash_mismatch_is_rejected(self):
        for field in ('archive', 'raw'):
            with self.subTest(field=field):
                checkpoint = copy.deepcopy(self.checkpoint)
                if field == 'archive':
                    checkpoint['artifacts'][0]['sha256'] = '0' * 64
                else:
                    trace = checkpoint['runs']['reference-off']['traces']['midi-event']
                    trace['raw_sha256'] = trace['captured_raw_sha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'hash differs'):
                    self.stage(checkpoint)

    def test_windowed_or_truncated_capture_is_rejected(self):
        for change in ({'scope': 'selected window'}, {'start_sample_inclusive': 1},
                       {'captured_rows': 3, 'retained_rows': 3}, {'discarded_rows': 1}):
            with self.subTest(change=change):
                checkpoint = copy.deepcopy(self.checkpoint)
                checkpoint['runs']['reference-off']['traces']['midi-event'].update(change)
                with self.assertRaises(ValueError):
                    self.stage(checkpoint)

    def test_saved_conflict_accounting_cannot_silently_change(self):
        checkpoint = copy.deepcopy(self.checkpoint)
        checkpoint['runs']['trial-on']['raw_midi_counts']['cross_pitch_on_before_release'] = 1
        with self.assertRaisesRegex(ValueError, 'evidence differs'):
            self.stage(checkpoint)

    def test_callbacks_must_be_unique_original_events_and_keep_counts(self):
        path = self.root / 'callbacks.tsv'
        header = ('# m3_ledger_callbacks_v1\n'
            'sample\tphase\tkind\tnote\tvelocity\tvoice_id\tchannel\tsource_sequence\n')
        rows = '1\tsource\ton\t60\t90\t0\t1\t0\n70\tsource\toff\t60\t0\t0\t1\t1\n'
        result = dict(input_events=2, source_callbacks=2, cleanup_callbacks=0,
            suppressed_source_events=0, callback_pairing_errors=0,
            host_delivery_verified=False, forced_eof_releases=False)
        path.write_text(header + rows)
        check_callbacks(path, result, self.source)
        for corrupted in (rows.replace('\t90\t', '\t91\t'), rows + rows.splitlines()[1] + '\n',
                          rows.replace('70\tsource', '70\tcleanup')):
            with self.subTest(corrupted=corrupted):
                path.write_text(header + corrupted)
                with self.assertRaises(ValueError):
                    check_callbacks(path, result, self.source)
        path.write_text(header + rows)
        with self.assertRaisesRegex(ValueError, 'accounting differs'):
            check_callbacks(path, dict(result, source_callbacks=1), self.source)


class NativeTests(unittest.TestCase):
    """Fail if the native target was not built; local callers select PureTests."""
    binary = Path('build/portable/m3_midi_ledger_replay').resolve()

    def setUp(self):
        self.assertTrue(self.binary.is_file(), 'Build m3_midi_ledger_replay on GitHub first')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def replay(self, rows, routing='single', samples=130, expected=None, raw=None):
        path, callbacks = self.root / 'events.tsv', self.root / 'callbacks.tsv'
        path.write_text(raw if raw is not None else event_text(rows))
        completed = subprocess.run([str(self.binary), str(path), str(samples),
            str(len(rows) if expected is None else expected), '64', routing, str(callbacks)],
            capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        source = dict(events=read_events(path, sample_count=samples, transition_count=len(rows)),
                      sample_count=samples)
        check_callbacks(callbacks, result, source)
        with callbacks.open() as stream:
            stream.readline()
            captured = list(csv.DictReader(stream, delimiter='\t'))
        return result, captured

    def test_assigned_unison_voices_keep_separate_callbacks_and_short_tail(self):
        rows = [(1, 'on', 60, 90, 0, 0), (1, 'on', 60, 91, 1, 1),
                (129, 'off', 60, 0, 0, 2), (129, 'off', 60, 0, 1, 3)]
        for routing, channels in (('single', ['1', '1']), ('per_voice', ['1', '2'])):
            with self.subTest(routing=routing):
                result, callbacks = self.replay(rows, routing)
                self.assertEqual(result['source_callbacks'], 4)
                self.assertEqual(result['last_block_frames'], 2)
                self.assertEqual(result['blocked_blocks'], 0)
                self.assertEqual(result['active_identities_at_eof'], [])
                self.assertEqual([row['channel'] for row in callbacks[:2]], channels)
                self.assertEqual([row['voice_id'] for row in callbacks[:2]], ['0', '1'])

    def test_same_sample_replacement_reorders_off_before_on(self):
        rows = [(1, 'on', 60, 90, 0, 0), (65, 'on', 62, 90, 0, 1),
                (65, 'off', 60, 0, 0, 2), (100, 'off', 62, 0, 0, 3)]
        result, callbacks = self.replay(rows)
        self.assertEqual(result['blocked_blocks'], 0)
        self.assertEqual([row['source_sequence'] for row in callbacks], ['0', '2', '1', '3'])

    def test_cross_sample_collision_blocks_then_releases_at_next_block(self):
        rows = [(1, 'on', 60, 90, 0, 0), (65, 'on', 62, 90, 0, 1),
                (66, 'off', 60, 0, 0, 2), (100, 'off', 62, 0, 0, 3)]
        for routing in ('single', 'per_voice'):
            with self.subTest(routing=routing):
                result, callbacks = self.replay(rows, routing)
                self.assertEqual(result['first_blocked_block_start'], 64)
                self.assertEqual(result['first_blocking_event']['sample'], 65)
                self.assertEqual(result['source_callbacks'], 1)
                self.assertEqual(result['suppressed_source_events'], 3)
                self.assertEqual(result['cleanup_callbacks'], 1)
                self.assertEqual(result['blocked_blocks'], 2)
                self.assertTrue(result['output_blocked_at_eof'])
                self.assertFalse(result['cleanup_pending_at_eof'])
                self.assertEqual(result['active_identities_at_eof'], [])
                self.assertEqual(callbacks[1]['sample'], '128')
                self.assertEqual(callbacks[1]['phase'], 'cleanup')

    def test_unassigned_duplicate_pitch_blocks(self):
        result, _ = self.replay([(1, 'on', 60, 90, 255, 0), (65, 'on', 60, 91, 255, 1)])
        self.assertEqual(result['first_blocking_event']['sequence'], 1)
        self.assertEqual(result['source_callbacks'], 1)
        self.assertEqual(result['cleanup_callbacks'], 1)

    def test_eof_open_is_retained_without_inventing_an_off(self):
        result, callbacks = self.replay([(129, 'on', 60, 90, 3, 0)], 'per_voice')
        self.assertEqual(result['active_identities_at_eof'], [dict(voice_id=3, note=60, channel=4)])
        self.assertEqual(len(callbacks), 1)
        self.assertFalse(result['forced_eof_releases'])
        self.assertFalse(result['host_delivery_verified'])

    def test_orphan_off_and_zero_velocity_on_report_first_blocking_event(self):
        for kind, velocity, rejected in (('off', 0, 0), ('on', 0, 1)):
            with self.subTest(kind=kind):
                result, callbacks = self.replay([(1, kind, 60, velocity, 0, 0)])
                self.assertEqual(result['first_blocked_block_start'], 0)
                self.assertEqual(result['first_blocking_event']['sample'], 1)
                self.assertEqual(result['queue_rejected_events'], rejected)
                self.assertEqual(callbacks, [])

    def test_incomplete_or_reordered_input_is_rejected_before_output_creation(self):
        rows = [(1, 'on', 60, 90, 0, 0), (70, 'off', 60, 0, 0, 1)]
        for raw, expected in ((event_text(rows), 3), (event_text(rows[::-1]), 2),
                              (event_text(rows).replace('m3_midi_events_v1', 'unknown'), 2)):
            with self.subTest(raw=raw, expected=expected):
                path, output = self.root / 'invalid.tsv', self.root / 'must-not-exist.tsv'
                path.write_text(raw)
                completed = subprocess.run([str(self.binary), str(path), '130', str(expected),
                    '64', 'single', str(output)], capture_output=True, text=True, timeout=10)
                self.assertEqual(completed.returncode, 2)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
