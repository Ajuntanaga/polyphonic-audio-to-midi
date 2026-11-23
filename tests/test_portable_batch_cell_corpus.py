"""Mock-only corpus contracts; no native execution or recording access."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests import test_portable_calibrated_midi_retention_timing as retention_tests
from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_assignment_trace import digest
from tools import portable_batch_cell_corpus as corpus_runner


TSV = retention_tests.RetentionTimingTests.TSV
MIDI = 'sample\tvoice\tnote\tevent\n64\t0\t52\ton\n128\t0\t52\toff\n'
SUMMARY = 'm3_replay: batch_cell_update enabled=1 supported=1 cells=245 guards=12\n'


class BatchCellCorpusTests(unittest.TestCase):
    def exercise(self, *, mutate_setup=None, mutate_run=None, timeout=900,
                 max_seconds=9000, clock=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, manifest, reference, output = (root / name for name in
                ('binary', 'manifest.json', 'reference.json', 'output'))
            binary.write_text('mock only; never executed')
            names = {'calibration.m3cb', 'templates.tsv'} | {
                name + suffix for name in corpus_runner.DATASETS for suffix in ('.wav', '.tsv')}
            for name in names:
                (root / name).write_text('mock input ' + name)
            source = dict(repository='Ajuntanaga/polyphonic-audio-to-midi',
                worker_repository='Ajuntanaga/m3-offload', provider='github-actions',
                commit=corpus_runner.ANCHOR_COMMIT, run_id='43756240245',
                input_release='corpus-20261108', input_bundle_sha256=corpus_runner.INPUT_SHA256,
                original_input_manifest_sha256=corpus_runner.MANIFEST_SHA256)
            manifest_data = dict(source=dict(source, commit='a' * 40, run_id='mock'),
                files={name: dict(sha256=digest(root / name)) for name in names})
            fixture = root / 'snapshot.tsv'
            fixture.write_text(TSV)
            baseline = dict(read_replay(fixture), tsv_sha256=digest(fixture))
            baseline.pop('labels')
            references = dict(schema=corpus_runner.REFERENCE_SCHEMA,
                anchor_report_sha256=corpus_runner.ANCHOR_SHA256, source=source,
                settings=corpus_runner.SETTINGS, conditions=corpus_runner.CONDITIONS,
                blocks=list(corpus_runner.BLOCKS), datasets={})
            for dataset in corpus_runner.DATASETS:
                rows = references['datasets'][dataset] = {}
                for block in corpus_runner.BLOCKS:
                    for mode in corpus_runner.CONDITIONS:
                        row = rows[f'{mode}-{block}'] = copy.deepcopy(baseline)
                        if block == 512:
                            row.update(midi_sha256=hashlib.sha256(MIDI.encode()).hexdigest(),
                                       midi_rows=2, sample_count=960, sample_rate=96000)
            if mutate_setup:
                mutate_setup(root, references, manifest_data)
            manifest.write_text(json.dumps(manifest_data))
            reference.write_text(json.dumps(references))
            commands, call_options = [], []

            def execute(command, **kwargs):
                index = len(commands)
                commands.append(command)
                call_options.append(dict(check=kwargs['check'], timeout=kwargs['timeout']))
                timing = dict(schema='m3_replay_core_timing_v1', sample_rate=96000,
                    block_samples=32, measurement_scope=corpus_runner.MEASUREMENT_SCOPE,
                    fingerprint='0123456789abcdef', fingerprint_identical=True,
                    allocation_guard=True, cpp_allocations=0, cpp_frees=0,
                    c_allocations=0, c_frees=0, p99_ns=100000, maximum_ns=200000,
                    deadline_overruns=0, blocks=30)
                streams = dict(tsv=TSV, stderr=SUMMARY, midi=MIDI)
                if '--midi-event-trace' in command:
                    streams['stderr'] += 'm3_replay: midi_event_trace rows=2 cap=1000000 truncated=0\n'
                if mutate_run:
                    mutate_run(index, timing, streams, command)
                kwargs['stdout'].write(streams['tsv'])
                kwargs['stderr'].write(streams['stderr'])
                if '--midi-event-trace' in command:
                    Path(command[command.index('--midi-event-trace') + 1]).write_text(streams['midi'])
                if '--diagnostic-core-timing' in command:
                    Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(json.dumps(timing))
                return subprocess.CompletedProcess(command, 0)

            error, passed = None, None
            with contextlib.ExitStack() as stack:
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                stack.enter_context(patch('tools.portable_batch_cell_corpus.subprocess.run',
                                          side_effect=execute))
                if clock:
                    stack.enter_context(patch('tools.portable_batch_cell_corpus.time.monotonic',
                                              side_effect=clock))
                try:
                    passed = corpus_runner.run(binary, root, manifest, reference, output,
                                               timeout=timeout, max_seconds=max_seconds)
                except Exception as caught:
                    error = caught
            report_path = output / 'report/report.json'
            report = json.loads(report_path.read_text()) if report_path.exists() else None
            return passed, report, error, commands, call_options

    def test_complete_fixed_corpus_preserves_references_and_measures_untraced_core(self):
        passed, report, error, commands, options = self.exercise()
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertEqual(len(commands), 126)
        for key, count in dict(snapshot_identities=126, midi_identities=42,
                buffer_identities=84, zero_allocation_runs=42, timing_runs_passed=42,
                timed_identity_runs=42, verified_inputs=30).items():
            self.assertEqual(report[key], count)
        self.assertTrue(report['collection_pass'])
        self.assertTrue(report['native_gate_pass'])
        self.assertFalse(report['promotion_accepted'])
        self.assertFalse(report['installed_output_changed'])
        self.assertEqual(report['live_readiness'], 'not measured')
        expected = [(dataset, block, flags) for dataset in corpus_runner.DATASETS
                    for block in corpus_runner.BLOCKS for flags in corpus_runner.CONDITIONS.values()]
        for command, (dataset, block, flags), option in zip(commands, expected, options):
            self.assertEqual(Path(command[command.index('--wav') + 1]).name, dataset + '.wav')
            self.assertEqual(command[command.index('--block') + 1], str(block))
            self.assertEqual(command.count(corpus_runner.FLAG), 1)
            self.assertEqual('--diagnostic-core-timing' in command, block == 32)
            self.assertEqual('--midi-event-trace' in command, block == 512)
            self.assertEqual([arg for arg in command if arg in {
                '--diagnostic-spectral-lane-collision', '--diagnostic-completion-midi-retention'}], flags)
            for prohibited in ('--diagnostic-thread-cpu', '--diagnostic-stage-cpu',
                               '--diagnostic-exact-cell-sharing', '--diagnostic-packed-cell-update'):
                self.assertNotIn(prohibited, command)
            self.assertTrue(option['check'])
            self.assertGreater(option['timeout'], 0)
            self.assertLessEqual(option['timeout'], 900)

    def test_wrong_reference_or_inputs_fail_before_execution(self):
        changes = (
            lambda root, refs, manifest: refs.update(anchor_report_sha256='0' * 64),
            lambda root, refs, manifest: refs['source'].update(commit='b' * 40),
            lambda root, refs, manifest: refs['datasets']['ordinary'].pop('current-on-32'),
            lambda root, refs, manifest: refs['datasets']['ordinary']['current-on-512'].pop('midi_sha256'),
            lambda root, refs, manifest: manifest['source'].update(input_bundle_sha256='c' * 64),
            lambda root, refs, manifest: manifest['files'].pop('physical-four.wav'),
            lambda root, refs, manifest: (root / 'ordinary.wav').write_text('changed input'))
        for change in changes:
            with self.subTest(change=change):
                _, report, error, commands, _ = self.exercise(mutate_setup=change)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(commands, [])
                self.assertEqual(report['state'], 'failed')
                self.assertTrue(report['final'])
                self.assertFalse(report['collection_pass'])

    def test_changed_snapshot_or_incomplete_midi_is_not_retried(self):
        changes = (
            lambda i, timing, streams, command: streams.update(tsv=TSV + '\n'),
            lambda i, timing, streams, command: streams.update(midi=MIDI.replace('128', '129')),
            lambda i, timing, streams, command: streams.update(stderr=streams['stderr'].replace('truncated=0', 'truncated=1')),
            lambda i, timing, streams, command: streams.update(stderr=streams['stderr'].replace('rows=2', 'rows=3')),
            lambda i, timing, streams, command: streams.update(stderr=streams['stderr'].replace('enabled=1', 'enabled=0')))
        for change in changes:
            with self.subTest(change=change):
                _, report, error, commands, _ = self.exercise(mutate_run=change)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(len(commands), 1)
                self.assertEqual(report['state'], 'failed')
                self.assertFalse(report['collection_pass'])

    def test_timing_and_allocation_failures_reject_but_finish_the_fixed_cases(self):
        def mutate(index, timing, streams, command):
            if index == 3:
                timing.update(maximum_ns=333334, deadline_overruns=1)
            if index == 4:
                timing.update(c_allocations=1)
        passed, report, error, commands, _ = self.exercise(mutate_run=mutate)
        self.assertIsNone(error)
        self.assertFalse(passed)
        self.assertEqual(len(commands), 126)
        self.assertEqual(report['snapshot_identities'], 126)
        self.assertEqual(report['timing_runs_passed'], 41)
        self.assertEqual(report['zero_allocation_runs'], 41)
        self.assertTrue(report['collection_pass'])
        self.assertFalse(report['native_gate_pass'])
        self.assertEqual(report['decision'], 'offline corpus rejected')

    def test_probe_contaminated_or_unmatched_timing_fails_closed(self):
        for change in (dict(thread_cpu={}), dict(stage_cpu={}), dict(allocation_trace={}),
                       dict(measurement_scope='wrong'), dict(fingerprint_identical=False)):
            with self.subTest(change=change):
                _, report, error, commands, _ = self.exercise(mutate_run=
                    lambda i, timing, streams, command: timing.update(change))
                self.assertIsInstance(error, ValueError)
                self.assertEqual(len(commands), 4)
                self.assertFalse(report['collection_pass'])
                self.assertTrue(report['final'])

    def test_buffer_identity_still_checks_labels_with_a_matching_saved_hash(self):
        changed = TSV.replace('0\t0\t960\t52', '0\t0\t961\t52')
        def setup(root, refs, manifest):
            refs['datasets']['ordinary']['reference-off-32']['tsv_sha256'] = hashlib.sha256(changed.encode()).hexdigest()
        def mutate(index, timing, streams, command):
            if index == 3:
                streams['tsv'] = changed
        _, report, error, commands, _ = self.exercise(mutate_setup=setup, mutate_run=mutate)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(len(commands), 4)
        self.assertTrue(report['datasets']['ordinary']['runs']['reference-off-32']['recorded_reference_bit_identical'])
        self.assertFalse(report['collection_pass'])

    def test_process_failure_or_timeout_preserves_partial_report_without_retry(self):
        for failure in (subprocess.CalledProcessError(1, 'mock'), subprocess.TimeoutExpired('mock', 900)):
            def mutate(index, timing, streams, command):
                if index == 1:
                    raise failure
            with self.subTest(failure=type(failure).__name__):
                _, report, error, commands, _ = self.exercise(mutate_run=mutate)
                self.assertIs(error, failure)
                self.assertEqual(len(commands), 2)
                self.assertEqual(report['snapshot_identities'], 1)
                self.assertTrue(report['final'])
                self.assertEqual(report['state'], 'failed')

    def test_expired_total_budget_does_not_launch_a_replay(self):
        _, report, error, commands, _ = self.exercise(max_seconds=1, clock=iter([0, 2]).__next__)
        self.assertIsInstance(error, TimeoutError)
        self.assertEqual(commands, [])
        self.assertFalse(report['collection_pass'])
        self.assertTrue(report['final'])


if __name__ == '__main__':
    unittest.main()
