"""Pure mocked runner contracts; never execute native code or open recordings."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_assignment_trace import digest
from tools.portable_completion_midi_retention_timing import (
    CONDITIONS, DATASETS, MEASUREMENT_SCOPE, REFERENCE_SCHEMA, SETTINGS)
from tools.portable_exact_cell_sharing import CASES, FLAG, run
from tests.test_portable_calibrated_midi_retention_timing import RetentionTimingTests


class ExactCellSharingTests(unittest.TestCase):
    def exercise(self, *, mutate_reference=None, mutate_run=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, manifest, reference, output = (root / name for name in
                ('binary', 'manifest.json', 'reference.json', 'output'))
            binary.write_text('mock, never executed')
            source = dict(input_release='retained', input_bundle_sha256='a' * 64,
                          original_input_manifest_sha256='b' * 64)
            manifest.write_text(json.dumps(dict(source=source)))
            retained = root / 'retained.tsv'
            retained.write_text(RetentionTimingTests.TSV)
            timing = dict(schema='m3_replay_core_timing_v1', sample_rate=96000,
                block_samples=32, blocks=32, measurement_scope=MEASUREMENT_SCOPE,
                fingerprint='0123456789abcdef', fingerprint_identical=True,
                allocation_guard=True, cpp_allocations=0, cpp_frees=0,
                c_allocations=0, c_frees=0, p99_ns=100000, maximum_ns=584577,
                deadline_overruns=4)
            baseline = dict(read_replay(retained), tsv_sha256=digest(retained), timing=timing)
            refs = dict(schema=REFERENCE_SCHEMA, source=source, settings=SETTINGS,
                block_samples=32, anchor_report_sha256='c' * 64,
                conditions={mode: list(flags) for mode, flags in CONDITIONS},
                datasets={name: {mode: copy.deepcopy(baseline) for mode, _ in CONDITIONS}
                          for name in DATASETS})
            if mutate_reference:
                mutate_reference(refs)
            reference.write_text(json.dumps(refs))
            commands = []

            def execute(command, **kwargs):
                index = len(commands)
                commands.append(command)
                enabled = FLAG in command
                timed = '--diagnostic-core-timing' in command
                observed = dict(timing, maximum_ns=200000, deadline_overruns=0,
                    total_ns=5000000, timing_diagnostic_only=True,
                    thread_cpu=dict(valid=True, block_resolution_pass=True,
                        total_ns=3800000 if enabled else 4000000,
                        p99_ns=95000 if enabled else 100000,
                        maximum_ns=190000, deadline_overruns=0,
                        phases=[dict(blocks=1, wall_deadline_overruns=0) for _ in range(32)],
                        slowest_blocks=[dict(wall_ns=200000, cpu_ns=190000, end_sample=32)]))
                kwargs['stdout'].write(RetentionTimingTests.TSV)
                if timed or enabled:
                    kwargs['stderr'].write('m3_replay: exact_cell_sharing '
                        f'enabled={int(enabled)} unique=154 duplicates=91\n')
                midi = None
                if not timed:
                    midi = Path(command[command.index('--midi-event-trace') + 1])
                    midi.write_text('sample\tvoice\tnote\tevent\n64\t0\t52\ton\n128\t0\t52\toff\n')
                    kwargs['stderr'].write('m3_replay: midi_event_trace rows=2 cap=1000000 truncated=0\n')
                if mutate_run:
                    mutate_run(index, observed, kwargs, command, midi)
                if timed:
                    Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(
                        json.dumps(observed))

            error, passed = None, None
            with patch('tools.portable_exact_cell_sharing.verify_inputs') as verify, \
                 patch('tools.portable_exact_cell_sharing.subprocess.run', side_effect=execute):
                try:
                    passed = run(binary, root, manifest, reference, output)
                except (ValueError, subprocess.TimeoutExpired) as caught:
                    error = caught
            report = json.loads((output / 'report/report.json').read_text())
            return passed, report, error, commands, verify.call_args_list

    def test_same_binary_twelve_fixed_runs_keep_tracing_out_of_timing(self):
        passed, report, error, commands, verified = self.exercise()
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertEqual([call.args[2] for call in verified], ['ordinary', 'physical-long'])
        self.assertEqual(len(commands), 12)
        self.assertEqual(len({command[0] for command in commands}), 1)
        for offset, block in ((0, 32), (6, 512)):
            for i, (dataset, mode) in enumerate(CASES):
                for j, arm in enumerate((False, True) if i % 2 == 0 else (True, False)):
                    command = commands[offset + 2 * i + j]
                    self.assertEqual(command[command.index('--block') + 1], str(block))
                    self.assertTrue(command[command.index('--wav') + 1].endswith('/' + dataset + '.wav'))
                    self.assertEqual(FLAG in command, arm)
                    self.assertEqual('--diagnostic-thread-cpu' in command, block == 32)
                    self.assertEqual('--diagnostic-core-timing' in command, block == 32)
                    self.assertEqual('--midi-event-trace' in command, block == 512)
                    for flag in dict(CONDITIONS)[mode]:
                        self.assertIn(flag, command)
        for case in report['cases']:
            self.assertTrue(case['raw_midi_bit_identical'])
            self.assertEqual(case['cpu_total_reduction_percent'], 5)
            for phase in ('timing_runs', 'midi_companions'):
                for row in case[phase].values():
                    self.assertTrue(row['observation_verified'])
                    self.assertTrue(row['recorded_reference_bit_identical'])
        self.assertTrue(report['collection_pass'])
        for key in ('native_gate_pass', 'promotion_accepted', 'installed_output_changed'):
            self.assertFalse(report[key])

    def test_wrong_reference_stops_before_execution(self):
        for change in (
                lambda r: r['source'].update(input_bundle_sha256='wrong'),
                lambda r: r['datasets'].pop('extended-high')):
            with self.subTest(change=change):
                _, report, error, commands, _ = self.exercise(mutate_reference=change)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(commands, [])
                self.assertEqual(report['state'], 'failed')

    def test_snapshot_change_fails_for_timed_and_untimed(self):
        for failure_at in (0, 6):
            def mutate(index, timing, streams, command, midi):
                if index == failure_at:
                    streams['stdout'].write('\n')
            _, report, error, commands, _ = self.exercise(mutate_run=mutate)
            self.assertIsInstance(error, ValueError)
            self.assertEqual(len(commands), failure_at + 1)
            self.assertFalse(report['collection_pass'])

    def test_changed_midi_fails_pair_identity(self):
        def mutate(index, timing, streams, command, midi):
            if index == 7:
                midi.write_text(midi.read_text().replace('52', '53'))
        _, report, error, commands, _ = self.exercise(mutate_run=mutate)
        self.assertIn('Paired raw MIDI', str(error))
        self.assertEqual(len(commands), 8)
        self.assertFalse(report['collection_pass'])

    def test_incomplete_midi_is_not_equal_evidence(self):
        def mutate(index, timing, streams, command, midi):
            if index == 6:
                streams['stderr'].seek(0)
                streams['stderr'].truncate()
                streams['stderr'].write('m3_replay: midi_event_trace rows=2 cap=2 truncated=1\n')
        _, report, error, commands, _ = self.exercise(mutate_run=mutate)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(len(commands), 7)
        self.assertFalse(report['collection_pass'])

    def test_allocation_and_clock_failures_stop_without_retry(self):
        for change in (
                lambda t: t.update(cpp_allocations=1),
                lambda t: t.update(fingerprint_identical=False),
                lambda t: t['thread_cpu'].update(block_resolution_pass=False),
                lambda t: t['thread_cpu'].update(total_ns=0)):
            with self.subTest(change=change):
                _, report, error, commands, _ = self.exercise(
                    mutate_run=lambda i, t, s, c, m: change(t))
                self.assertIsInstance(error, ValueError)
                self.assertEqual(len(commands), 1)
                self.assertTrue(report['final'])

    def test_mode_and_cell_map_must_be_exercised_and_identical(self):
        for text in (
                'enabled=1 unique=154 duplicates=91',
                'enabled=0 unique=245 duplicates=0',
                'enabled=0 unique=155 duplicates=90'):
            def mutate(index, timing, streams, command, midi):
                if index == 0:
                    streams['stderr'].seek(0)
                    streams['stderr'].truncate()
                    streams['stderr'].write('m3_replay: exact_cell_sharing ' + text + '\n')
            _, report, error, commands, _ = self.exercise(mutate_run=mutate)
            self.assertIsInstance(error, ValueError)
            self.assertLessEqual(len(commands), 2)
            self.assertFalse(report['collection_pass'])

    def test_small_gain_or_worse_p99_is_scientific_rejection(self):
        for change in (
                lambda t: t['thread_cpu'].update(total_ns=3920001),
                lambda t: t['thread_cpu'].update(p99_ns=100001)):
            def mutate(index, timing, streams, command, midi):
                if index == 1:
                    change(timing)
            passed, report, error, commands, _ = self.exercise(mutate_run=mutate)
            self.assertIsNone(error)
            self.assertFalse(passed)
            self.assertEqual(len(commands), 12)
            self.assertTrue(report['collection_pass'])
            self.assertEqual(report['state'], 'completed')

    def test_exact_two_percent_and_unchanged_p99_pass_usefulness(self):
        def mutate(index, timing, streams, command, midi):
            if FLAG in command:
                timing['thread_cpu'].update(total_ns=3920000, p99_ns=100000)
        passed, _, error, _, _ = self.exercise(mutate_run=mutate)
        self.assertIsNone(error)
        self.assertTrue(passed)

    def test_timeout_retains_captured_partial_run_and_does_not_retry(self):
        def mutate(index, timing, streams, command, midi):
            if index == 2:
                raise subprocess.TimeoutExpired('mock replay', 900)
        _, report, error, commands, _ = self.exercise(mutate_run=mutate)
        self.assertIsInstance(error, subprocess.TimeoutExpired)
        self.assertEqual(len(commands), 3)
        self.assertEqual(report['state'], 'failed')
        self.assertTrue(report['cases'][0]['timing_runs']['on']['observation_verified'])
        self.assertFalse(report['cases'][1]['timing_runs']['on']['observation_verified'])


if __name__ == '__main__':
    unittest.main()
