"""Small file fixtures only; no native replay or recorded audio is executed."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_unfiltered_observation as observation


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ObservationRoutingTests(unittest.TestCase):
    snapshot = b'synthetic snapshot\n'
    midi = b'synthetic MIDI\n'
    trace = b'synthetic candidate trace\n'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.corpus = self.root / 'corpus'
        self.corpus.mkdir()
        self.binary = self.root / 'replay-placeholder'
        self.binary.write_bytes(b'not executable')
        self.manifest = self.root / 'manifest.json'
        self.reference = self.root / 'reference.json'
        self.output = self.root / 'result'

    def fixture(self, dataset):
        files = {}
        for name in (dataset + '.wav', dataset + '.tsv',
                     'calibration.m3cb', 'templates.tsv'):
            data = ('synthetic ' + name).encode()
            (self.corpus / name).write_bytes(data)
            files[name] = dict(bytes=len(data), sha256=sha(data))
        source = dict(input_release='synthetic', input_bundle_sha256='bundle',
                      original_input_manifest_sha256='manifest')
        self.manifest.write_text(json.dumps(dict(source=source, files=files)))
        ref = dict(dataset=dataset, settings=observation.SETTINGS, block_samples=512,
                   reference_flags={'current-on': ['--diagnostic-spectral-lane-collision']},
                   inputs=files, source=source,
                   runs={'current-on': dict(tsv_sha256=sha(self.snapshot),
                                            midi_trace_sha256=sha(self.midi))})
        self.reference.write_text(json.dumps(ref))
        return ref

    def fake_replay(self, command, *, stdout, stderr, check, timeout):
        self.assertTrue(check)
        stdout.write(self.snapshot.decode())
        Path(command[command.index('--midi-event-trace') + 1]).write_bytes(self.midi)
        if '--outcome-trace' in command:
            Path(command[command.index('--outcome-trace') + 1]).write_bytes(self.trace)

    def run_observation(self, **kwargs):
        return observation.run(self.binary, self.corpus, self.manifest,
                               self.reference, self.output, **kwargs)

    def test_extended_middle_routes_all_three_identity_companions(self):
        self.fixture('extended-middle')
        with patch.object(observation.subprocess, 'run', side_effect=self.fake_replay) as replay:
            report = self.run_observation(dataset='extended-middle')
        self.assertEqual(replay.call_count, 3)
        self.assertEqual(report['state'], 'completed')
        self.assertFalse(report['installed_output_changed'])
        self.assertEqual(report['historical_v4_trace_identity']['state'], 'unavailable')
        for mode, item in report['runs'].items():
            command = item['command']
            self.assertIn(str(self.corpus / 'extended-middle.wav'), command)
            self.assertIn(str(self.corpus / 'extended-middle.tsv'), command)
            self.assertIn('--diagnostic-spectral-lane-collision', command)
            self.assertEqual('--outcome-trace-annotations' in command, mode == 'v5')
            self.assertEqual('--outcome-trace' in command, mode != 'untraced')
            self.assertTrue(item['saved_identity'])
            self.assertEqual(item['snapshot_sha256'], sha(self.snapshot))
            self.assertEqual(item['midi_sha256'], sha(self.midi))
        with gzip.open(self.output / 'extended-middle-current-on-512-outcome-v5.tsv.gz', 'rb') as stream:
            self.assertEqual(stream.read(), self.trace)

    def test_ordinary_default_keeps_legacy_trace_guard(self):
        self.fixture('ordinary')
        with patch.object(observation.subprocess, 'run', side_effect=self.fake_replay), \
                patch.object(observation, 'LEGACY_SHA', sha(self.trace)):
            report = self.run_observation()
        self.assertEqual(report['dataset'], 'ordinary')
        self.assertEqual(report['historical_v4_trace_identity']['state'], 'passed')

    def test_ordinary_legacy_mismatch_stops_before_v5(self):
        self.fixture('ordinary')
        with patch.object(observation.subprocess, 'run', side_effect=self.fake_replay) as replay:
            with self.assertRaisesRegex(ValueError, 'Legacy trace differs'):
                self.run_observation()
        self.assertEqual(replay.call_count, 2)
        report = json.loads((self.output / 'report.json').read_text())
        self.assertEqual(report['state'], 'failed')
        self.assertEqual(report['historical_v4_trace_identity']['state'], 'failed')
        self.assertNotIn('v5', report['runs'])

    def test_wrong_reference_dataset_does_not_execute(self):
        self.fixture('ordinary')
        with patch.object(observation.subprocess, 'run') as replay:
            with self.assertRaisesRegex(ValueError, 'Reference dataset mismatch'):
                self.run_observation(dataset='extended-middle')
        replay.assert_not_called()

    def test_incomplete_reference_input_set_does_not_execute(self):
        ref = self.fixture('extended-middle')
        del ref['inputs']['templates.tsv']
        self.reference.write_text(json.dumps(ref))
        with patch.object(observation.subprocess, 'run') as replay:
            with self.assertRaisesRegex(ValueError, 'Reference input set mismatch'):
                self.run_observation(dataset='extended-middle')
        replay.assert_not_called()

    def test_changed_input_does_not_execute(self):
        self.fixture('extended-middle')
        (self.corpus / 'extended-middle.tsv').write_bytes(b'changed')
        with patch.object(observation.subprocess, 'run') as replay:
            with self.assertRaisesRegex(ValueError, 'Input identity failed'):
                self.run_observation(dataset='extended-middle')
        replay.assert_not_called()

    def test_changed_snapshot_or_midi_stops_after_first_companion(self):
        for field in ('tsv_sha256', 'midi_trace_sha256'):
            with self.subTest(field=field):
                self.output = self.root / field
                ref = self.fixture('extended-middle')
                ref['runs']['current-on'][field] = sha(b'different')
                self.reference.write_text(json.dumps(ref))
                with patch.object(observation.subprocess, 'run', side_effect=self.fake_replay) as replay:
                    with self.assertRaisesRegex(ValueError, 'saved snapshot or raw MIDI identity failed'):
                        self.run_observation(dataset='extended-middle')
                self.assertEqual(replay.call_count, 1)
                report = json.loads((self.output / 'report.json').read_text())
                self.assertEqual(report['state'], 'failed')
                self.assertNotIn('v4', report['runs'])


if __name__ == '__main__':
    unittest.main()
