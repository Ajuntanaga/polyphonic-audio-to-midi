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
    CONDITIONS, DATASETS, MEASUREMENT_SCOPE, REFERENCE_SCHEMA, SETTINGS, STAGE_CONTROLS, run)
from tools.portable_controlled_replay import STAGES
from tests import test_portable_calibrated_midi_retention_timing as legacy_timing_tests


class CompletionTimingTests(unittest.TestCase):
    def exercise(self, *, mutate_reference=None, mutate_run=None, stage_diagnosis=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, manifest, reference, output = (root / name for name in
                ('binary', 'manifest.json', 'reference.json', 'output'))
            binary.write_text('not executed')
            source = dict(input_release='retained', input_bundle_sha256='a' * 64,
                          original_input_manifest_sha256='b' * 64)
            manifest.write_text(json.dumps(dict(source=source)))
            retained = root / 'retained.tsv'
            retained.write_text(legacy_timing_tests.RetentionTimingTests.TSV)
            timing = dict(schema='m3_replay_core_timing_v1', sample_rate=96000,
                block_samples=32, blocks=334080 if stage_diagnosis else 32,
                measurement_scope=MEASUREMENT_SCOPE,
                fingerprint='0123456789abcdef', fingerprint_identical=True,
                allocation_guard=True,
                cpp_allocations=0, cpp_frees=0, c_allocations=0, c_frees=0,
                p99_ns=100000, maximum_ns=584577, deadline_overruns=4)
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
                observed = dict(timing, maximum_ns=200000, deadline_overruns=0,
                    timing_diagnostic_only=True, thread_cpu=dict(
                        valid=True, block_resolution_pass=True,
                        phases=[dict(blocks=timing['blocks'] // 32, wall_deadline_overruns=0)
                                for _ in range(32)],
                        slowest_blocks=[dict(wall_ns=200000, cpu_ns=190000, end_sample=32)]))
                if stage_diagnosis:
                    def stage_block(sample):
                        return dict(end_sample=sample, cpu_ns=190000, wall_ns=200000,
                            unattributed_cpu_ns=10000,
                            stages={name: dict(ns=20000, calls=1) for name in STAGES})
                    controls = [int(command[i + 1]) for i, arg in enumerate(command)
                                if arg == '--diagnostic-stage-end-sample']
                    observed['thread_cpu'].update(maximum_ns=190000, total_ns=1900000)
                    observed['stage_cpu'] = dict(valid=True, blocks=timing['blocks'],
                        totals={name: dict(ns=20000, calls=1) for name in STAGES},
                        slowest_cpu_blocks=[stage_block(32)],
                        control_cpu_blocks=[stage_block(sample) for sample in controls])
                kwargs['stdout'].write(legacy_timing_tests.RetentionTimingTests.TSV)
                if mutate_run:
                    mutate_run(index, observed, kwargs['stdout'])
                Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(
                    json.dumps(observed))

            error, passed = None, None
            with patch('tools.portable_completion_midi_retention_timing.verify_inputs') as verify, \
                 patch('tools.portable_completion_midi_retention_timing.subprocess.run',
                       side_effect=execute):
                try:
                    passed = run(binary, root, manifest, reference, output,
                                 stage_diagnosis=stage_diagnosis)
                except (ValueError, subprocess.TimeoutExpired) as caught:
                    error = caught
            report = json.loads((output / 'report.json').read_text())
            return passed, report, error, commands, verify.call_args_list

    def test_nine_fixed_replays_preserve_identity_and_cannot_clear_saved_failures(self):
        passed, report, error, commands, verified = self.exercise()
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertEqual([call.args[2] for call in verified], list(DATASETS))
        self.assertEqual(len(commands), 9)
        for command, (dataset, mode, flags) in zip(commands,
                ((ds, mode, flags) for ds in DATASETS for mode, flags in CONDITIONS)):
            self.assertEqual(command[command.index('--block') + 1], '32')
            self.assertTrue(command[command.index('--wav') + 1].endswith('/' + dataset + '.wav'))
            self.assertEqual([arg for arg in command if arg.startswith('--diagnostic-')],
                ['--diagnostic-core-timing', *flags, '--diagnostic-thread-cpu'])
            row = report['datasets'][dataset][mode]
            self.assertTrue(row['recorded_reference_bit_identical'])
            self.assertFalse(row['gates']['timing_pass'])
            self.assertFalse(row['gates']['zero_processing_allocations'])
            self.assertEqual(row['saved_uninstrumented_timing']['maximum_ns'], 584577)
        self.assertTrue(report['collection_pass'])
        self.assertFalse(report['native_gate_pass'])
        self.assertFalse(report['promotion_accepted'])

    def test_bad_reference_selection_or_provenance_stops_before_execution(self):
        changes = (
            lambda r: r['datasets'].pop('extended-high'),
            lambda r: r['conditions'].update({'current-on': []}),
            lambda r: r['source'].update(input_bundle_sha256='different'),
            lambda r: r['datasets']['ordinary'].pop('current-on'),
            lambda r: r['datasets']['physical-long']['current-on']['timing'].update(thread_cpu={}),
            lambda r: r['datasets']['extended-high']['current-on']['timing'].update(block_samples=512))
        for change in changes:
            with self.subTest(change=change):
                _, report, error, commands, _ = self.exercise(mutate_reference=change)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(commands, [])
                self.assertEqual(report['state'], 'failed')

    def test_hash_scope_block_count_and_slow_sample_evidence_are_required(self):
        changes = (
            lambda i, t, out: out.write('\n'),
            lambda i, t, out: t.update(measurement_scope='old scope'),
            lambda i, t, out: t.update(fingerprint_identical=False),
            lambda i, t, out: t.update(blocks=33),
            lambda i, t, out: t['thread_cpu'].update(phases=[]),
            lambda i, t, out: t['thread_cpu']['slowest_blocks'][0].pop('end_sample'))
        for change in changes:
            with self.subTest(change=change):
                _, report, error, commands, _ = self.exercise(mutate_run=change)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(len(commands), 1)
                self.assertFalse(report['collection_pass'])
                self.assertTrue(report['final'])

    def test_timeout_preserves_partial_results_and_stops_without_retry(self):
        def fail_third(index, timing, out):
            if index == 2:
                raise subprocess.TimeoutExpired('mock replay', 900)
        _, report, error, commands, _ = self.exercise(mutate_run=fail_third)
        self.assertIsInstance(error, subprocess.TimeoutExpired)
        self.assertEqual(len(commands), 3)
        self.assertEqual(len(report['datasets']['ordinary']), 2)
        self.assertEqual(report['state'], 'failed')
        self.assertFalse(report['collection_pass'])

    def test_low_resolution_is_collected_without_cpu_attribution(self):
        passed, report, error, _, _ = self.exercise(mutate_run=lambda i, t, out:
            t['thread_cpu'].update(block_resolution_pass=False))
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertFalse(report['cpu_block_statistics_usable'])
        self.assertFalse(report['native_gate_pass'])

    def test_three_stage_replays_retain_four_fixed_controls_without_acceptance(self):
        passed, report, error, commands, verified = self.exercise(stage_diagnosis=True)
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertEqual([call.args[2] for call in verified], ['ordinary', 'physical-long'])
        self.assertEqual(len(commands), 3)
        self.assertEqual(report['schema'], 'm3_completion_midi_retention_stages_v1')
        self.assertEqual(report['stage_anchor']['run_id'], 43774069298)
        for command, ((ds, mode), expected) in zip(commands, STAGE_CONTROLS.items()):
            self.assertEqual([int(command[i + 1]) for i, arg in enumerate(command)
                if arg == '--diagnostic-stage-end-sample'], list(expected))
            self.assertEqual([arg for arg in command if arg in dict(CONDITIONS)[mode]],
                             list(dict(CONDITIONS)[mode]))
            row = report['datasets'][ds][mode]
            self.assertTrue(row['stage_controls_verified'])
            self.assertTrue(row['recorded_reference_bit_identical'])
            self.assertEqual(row['saved_uninstrumented_timing']['maximum_ns'], 584577)
            self.assertFalse(row['gates']['timing_pass'])
        self.assertFalse(report['native_gate_pass'])
        self.assertFalse(report['promotion_accepted'])

    def test_stage_controls_require_complete_nonoverlapping_usable_measurements(self):
        changes = (
            lambda i, t, out: t.pop('stage_cpu'),
            lambda i, t, out: t['stage_cpu']['control_cpu_blocks'].clear(),
            lambda i, t, out: t['stage_cpu']['control_cpu_blocks'][0].update(end_sample=32),
            lambda i, t, out: t['stage_cpu']['control_cpu_blocks'][0]['stages'].pop('selection'),
            lambda i, t, out: t['stage_cpu']['control_cpu_blocks'][0].update(unattributed_cpu_ns=1),
            lambda i, t, out: t['stage_cpu']['control_cpu_blocks'][0].update(wall_ns=-1),
            lambda i, t, out: t['thread_cpu'].update(block_resolution_pass=False),
            lambda i, t, out: t.update(cpp_allocations=1))
        for change in changes:
            with self.subTest(change=change):
                _, report, error, commands, _ = self.exercise(
                    stage_diagnosis=True, mutate_run=change)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(len(commands), 1)
                self.assertFalse(report['collection_pass'])


if __name__ == '__main__':
    unittest.main()
