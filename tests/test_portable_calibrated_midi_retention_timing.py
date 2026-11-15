import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_assignment_trace import digest
from tools.portable_calibrated_midi_retention_timing import (
    CONDITIONS, DATASET, MEASUREMENT_SCOPE, REFERENCE_SCHEMA, SETTINGS, run)


class RetentionTimingTests(unittest.TestCase):
    TSV = (
        'labeled\tmatched\tfalse_wrong_note_voices\tfalse_wrong_string_voices\t'
        'false_gap_voices\tfalse_positive_voices\tfingerprint\n'
        '10\t8\t1\t0\t2\t3\t0123456789abcdef\n'
        'label_index\tstart_sample\tend_sample\tmidi_note\tstring_mask\t'
        'calibration_pass\tlabeled\tmatched\n'
        '0\t0\t960\t52\t1\t1\t10\t8\n')

    def exercise(self, *, mutate_reference=None, mutate_run=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, manifest, reference, output = (root / name for name in
                ('binary', 'manifest.json', 'reference.json', 'output'))
            binary.write_text('not executed')
            source = dict(input_release='retained', input_bundle_sha256='a' * 64,
                          original_input_manifest_sha256='b' * 64)
            manifest.write_text(json.dumps(dict(source=source)))
            retained = root / 'retained.tsv'
            retained.write_text(self.TSV)
            timing = dict(schema='m3_replay_core_timing_v1', sample_rate=96000,
                block_samples=32, measurement_scope=MEASUREMENT_SCOPE,
                fingerprint='0123456789abcdef', fingerprint_identical=True,
                allocation_guard=True,
                cpp_allocations=0, cpp_frees=0, c_allocations=0, c_frees=0,
                p99_ns=100000, maximum_ns=737423, deadline_overruns=7)
            baseline = dict(read_replay(retained), tsv_sha256=digest(retained), timing=timing)
            refs = dict(schema=REFERENCE_SCHEMA, source=source, dataset=DATASET,
                settings=SETTINGS, block_samples=32, anchor_report_sha256='c' * 64,
                conditions={mode: list(flags) for mode, flags in CONDITIONS},
                runs={mode: baseline for mode, _ in CONDITIONS})
            if mutate_reference:
                mutate_reference(refs)
            reference.write_text(json.dumps(refs))
            commands = []

            def execute(command, **kwargs):
                index = len(commands)
                commands.append(command)
                observed = dict(timing, maximum_ns=200000, deadline_overruns=0,
                    blocks=32, timing_diagnostic_only=True, thread_cpu=dict(
                        valid=True, block_resolution_pass=True,
                        phases=[dict(blocks=1, wall_deadline_overruns=0) for _ in range(32)],
                        slowest_blocks=[dict(wall_ns=200000, cpu_ns=190000, end_sample=32)]))
                kwargs['stdout'].write(self.TSV)
                if mutate_run:
                    mutate_run(index, observed, kwargs['stdout'])
                Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(
                    json.dumps(observed))

            error, passed = None, None
            with patch('tools.portable_calibrated_midi_retention_timing.verify_inputs'), \
                 patch('tools.portable_calibrated_midi_retention_timing.subprocess.run',
                       side_effect=execute):
                try:
                    passed = run(binary, root, manifest, reference, output)
                except ValueError as caught:
                    error = caught
            report = json.loads((output / 'report.json').read_text())
            return passed, report, error, commands

    def test_exact_three_profiles_collect_but_cannot_clear_saved_failure(self):
        passed, report, error, commands = self.exercise()
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertEqual(len(commands), 3)
        for command, (mode, flags) in zip(commands, CONDITIONS):
            self.assertEqual(command[command.index('--block') + 1], '32')
            self.assertTrue(command[command.index('--wav') + 1].endswith('/isolated-05.wav'))
            self.assertEqual([arg for arg in command if arg in {
                flag for _, profile in CONDITIONS for flag in profile}], list(flags))
            self.assertIn('--diagnostic-thread-cpu', command)
            row = report['runs'][mode]
            self.assertTrue(row['recorded_reference_bit_identical'])
            self.assertFalse(row['gates']['timing_pass'])
            self.assertFalse(row['gates']['zero_processing_allocations'])
            self.assertEqual(row['saved_uninstrumented_timing']['maximum_ns'], 737423)
        self.assertTrue(report['collection_pass'])
        self.assertFalse(report['native_gate_pass'])
        self.assertFalse(report['promotion_accepted'])
        self.assertEqual(report['acceptance'], 'not evaluated: diagnostic timing')

    def test_wrong_reference_selection_or_input_provenance_stops_before_execution(self):
        changes = (
            lambda r: r.update(dataset='ordinary'),
            lambda r: r['conditions'].update({'current-on': []}),
            lambda r: r['source'].update(input_bundle_sha256='different'),
            lambda r: r['runs'].pop('current-on'),
            lambda r: r['runs']['current-on']['timing'].update(timing_diagnostic_only=True),
            lambda r: r['runs']['current-on']['timing'].update(thread_cpu={}))
        for change in changes:
            with self.subTest(change=change):
                _, report, error, commands = self.exercise(mutate_reference=change)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(commands, [])
                self.assertEqual(report['state'], 'failed')

    def test_identical_counts_do_not_excuse_changed_tsv_or_missing_cpu_data(self):
        changes = (
            lambda i, timing, out: out.write('\n'),
            lambda i, timing, out: timing.update(measurement_scope='old scope'),
            lambda i, timing, out: timing.update(fingerprint_identical=False),
            lambda i, timing, out: timing['thread_cpu'].update(phases=[]))
        for change in changes:
            with self.subTest(change=change):
                _, report, error, commands = self.exercise(mutate_run=change)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(len(commands), 1)
                self.assertFalse(report['collection_pass'])
                self.assertTrue(report['final'])

    def test_low_clock_resolution_is_reported_without_claiming_cpu_attribution(self):
        passed, report, error, _ = self.exercise(mutate_run=lambda i, timing, out:
            timing['thread_cpu'].update(block_resolution_pass=False))
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertFalse(report['cpu_block_statistics_usable'])
        self.assertFalse(report['native_gate_pass'])


if __name__ == '__main__':
    unittest.main()
