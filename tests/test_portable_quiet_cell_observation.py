"""Generated text and mocked commands only; no recorded audio/native execution."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_quiet_cell_observation as observation


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tuple_for(note):
    return ':'.join([str(note)] + ['0'] * 45)


def v5_text():
    return ('# m3_candidate_outcome_v5\n' + '\t'.join(observation.V5_HEADER) + '\n' +
            '\t'.join(['63', '1', '5', '0', '0:40:1', '', '',
                       tuple_for(40) + ',' + tuple_for(52), '0.125', '0']) + '\n' +
            '\t'.join(['127', '2', '0', '64', '', '', '', tuple_for(40), '0.25', '0']) + '\n')


def cell_row(sample, tick, quiet, note, available, power):
    numbers = ([str(power), '0.99', '100', '0.05', '-0.01'] + ['0'] * 15
               if available else ['0'] * 20)
    return '\t'.join(list(map(str, (sample, tick, quiet, note, available))) + numbers) + '\n'


def cell_text():
    return ('# m3_outcome_cells_v1\n' + '\t'.join(observation.CELL_HEADER) + '\n' +
            cell_row(63, 1, 5, 40, 1, 0.125) + cell_row(63, 1, 5, 52, 0, 0) +
            cell_row(127, 2, 0, 40, 1, 0.25))


class QuietCellTests(unittest.TestCase):
    snapshot = b'generated snapshot\n'
    midi = b'generated MIDI\n'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.corpus = self.root / 'corpus'
        self.corpus.mkdir()
        self.binary = self.root / 'not-an-executable'
        self.binary.write_bytes(b'placeholder')
        self.spec = self.root / 'spec.json'
        self.manifest = self.root / 'manifest.json'
        self.output = self.root / 'result'
        self.trace = self.root / 'v5.tsv'
        self.cells = self.root / 'cells.tsv'
        self.trace.write_text(v5_text())
        self.cells.write_text(cell_text())
        files = {}
        for name in ('ordinary.wav', 'ordinary.tsv', 'extended-middle.wav',
                     'extended-middle.tsv', 'calibration.m3cb', 'templates.tsv'):
            data = ('generated ' + name).encode()
            (self.corpus / name).write_bytes(data)
            files[name] = dict(bytes=len(data), sha256=sha(data))
        source = dict(input_release='fixture', input_bundle_sha256='bundle',
                      original_input_manifest_sha256='manifest')
        self.manifest.write_text(json.dumps(dict(source=source, files=files)))
        datasets = {}
        for dataset in observation.DATASETS:
            ref_path = self.root / (dataset + '-ref.json')
            ref = dict(dataset=dataset, settings=observation.SETTINGS, block_samples=512,
                       reference_flags={'current-on': observation.FLAGS}, source=source,
                       inputs={name: files[name] for name in
                               (dataset+'.wav', dataset+'.tsv', 'calibration.m3cb', 'templates.tsv')},
                       runs={'current-on': dict(tsv_sha256=sha(self.snapshot),
                                                midi_trace_sha256=sha(self.midi))})
            ref_path.write_text(json.dumps(ref))
            datasets[dataset] = dict(reference=str(ref_path), v5_sha256=sha(v5_text().encode()))
        self.frozen = dict(schema='m3_quiet_cell_observation_spec_v1', datasets=datasets,
                           companions=list(observation.MODES), block_samples=512,
                           flags=observation.FLAGS, policy_change=False,
                           installed_output_changed=False, automatic_retry=False)
        self.spec.write_text(json.dumps(self.frozen))

    def fake_replay(self, command, *, stdout, stderr, check, timeout):
        self.assertTrue(check)
        self.assertEqual(timeout, 1200)
        stdout.write(self.snapshot.decode())
        Path(command[command.index('--midi-event-trace') + 1]).write_bytes(self.midi)
        if '--outcome-trace' in command:
            Path(command[command.index('--outcome-trace') + 1]).write_text(v5_text())
        if '--outcome-cell-trace' in command:
            Path(command[command.index('--outcome-cell-trace') + 1]).write_text(cell_text())

    def execute(self):
        return observation.run(self.binary, self.corpus, self.manifest, self.spec, self.output)

    def test_streaming_coverage_keeps_unavailable_and_quiet_measurements(self):
        result = observation.validate_sidecar(self.trace, self.cells)
        self.assertEqual(result['frames'], 2)
        self.assertEqual(result['rows'], 3)
        self.assertEqual(result['quiet_counts']['5'],
                         dict(ticks=1, rows=2, available=1, nonzero_cells=1))

    def test_missing_extra_reordered_and_nonfinite_fail(self):
        lines = cell_text().splitlines(keepends=True)
        bad = [lines[:-1], lines + [lines[-1]],
               lines[:2] + [lines[3], lines[2], lines[4]],
               [line.replace('0.05', 'nan') for line in lines],
               [line.replace('0.125', '-0.125') for line in lines],
               [line.replace('0.125', '0.126') for line in lines],
               [line.replace('0.99', '1.01') for line in lines],
               [line.replace('\t100\t', '\t-100\t') for line in lines]]
        for i, rows in enumerate(bad):
            with self.subTest(i=i):
                self.cells.write_text(''.join(rows))
                with self.assertRaises(ValueError):
                    observation.validate_sidecar(self.trace, self.cells)

    def test_unavailable_is_not_silence_or_measured_power(self):
        self.cells.write_text(cell_text().replace('52\t0\t0', '52\t0\t0.125'))
        with self.assertRaisesRegex(ValueError, 'Unavailable'):
            observation.validate_sidecar(self.trace, self.cells)

    def test_six_companions_preserve_all_identities_and_compress_remote_evidence(self):
        with patch.object(observation.subprocess, 'run', side_effect=self.fake_replay) as replay:
            report = self.execute()
        self.assertEqual(replay.call_count, 6)
        self.assertEqual(report['state'], 'completed')
        self.assertFalse(report['policy_change'])
        for dataset, entry in report['datasets'].items():
            for mode, item in entry['runs'].items():
                command = item['command']
                self.assertIn(str(self.corpus / (dataset + '.wav')), command)
                self.assertTrue(item['saved_identity'])
                self.assertEqual('--outcome-cell-trace' in command, mode == 'cells')
                self.assertEqual('--outcome-trace-annotations' in command, mode != 'untraced')
                self.assertEqual([x for x in command if x.startswith('--diagnostic-')], observation.FLAGS)
            self.assertEqual(entry['runs']['cells']['coverage']['rows'], 3)
            for item in entry['runs']['cells']['evidence']:
                path = self.output / 'bulk' / item['path']
                self.assertEqual(sha(path.read_bytes()), item['sha256'])
                with gzip.open(path, 'rb') as zipped:
                    self.assertEqual(sha(zipped.read()), item['raw_sha256'])
                self.assertFalse(path.with_suffix('').exists())

    def test_bad_second_input_prevents_any_execution(self):
        (self.corpus / 'extended-middle.tsv').write_bytes(b'changed')
        with patch.object(observation.subprocess, 'run') as replay:
            with self.assertRaisesRegex(ValueError, 'Input identity failed'):
                self.execute()
        replay.assert_not_called()

    def test_v5_identity_failure_stops_before_cells(self):
        self.frozen['datasets']['ordinary']['v5_sha256'] = sha(b'wrong')
        self.spec.write_text(json.dumps(self.frozen))
        with patch.object(observation.subprocess, 'run', side_effect=self.fake_replay) as replay:
            with self.assertRaisesRegex(ValueError, 'historical v5 identity failed'):
                self.execute()
        self.assertEqual(replay.call_count, 2)
        report = json.loads((self.output / 'report/report.json').read_text())
        self.assertEqual(report['state'], 'failed')
        self.assertNotIn('cells', report['datasets']['ordinary']['runs'])

    def test_policy_flag_or_retry_is_rejected_before_execution(self):
        for key, value in (('automatic_retry', True), ('flags', observation.FLAGS + ['--other'])):
            with self.subTest(key=key):
                self.output = self.root / key
                spec = dict(self.frozen)
                spec[key] = value
                self.spec.write_text(json.dumps(spec))
                with patch.object(observation.subprocess, 'run') as replay:
                    with self.assertRaisesRegex(ValueError, 'specification mismatch'):
                        self.execute()
                replay.assert_not_called()


if __name__ == '__main__':
    unittest.main()
