from pathlib import Path
from itertools import product
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.portable_corpus_replay import MEASUREMENT_SCOPE, command_for, timing_gates, main
from tools.midi_lifecycle_analysis import CONFLICT_FIELDS
from tools.replay_corpus import DATASETS


class PortableCorpusTests(unittest.TestCase):
    def test_actual_correction_requires_both_flags_and_leaves_reset_switch_off(self):
        arguments = (Path('/replay'), Path('/corpus'), 'physical-long')
        off = command_for(*arguments, 'off', 32, Path('/off.json'))
        on = command_for(*arguments, 'on', 32, Path('/on.json'))
        for flag in ('--diagnostic-native-partial-cues', '--diagnostic-cue-free-lane-reassignment'):
            self.assertNotIn(flag, off)
            self.assertIn(flag, on)
        self.assertNotIn('--diagnostic-skip-empty-fine-reset', on)
        self.assertIn('--label-details', on)

    def test_preview_trial_is_isolated_from_cue_and_reset_corrections(self):
        arguments = (Path('/replay'), Path('/corpus'), 'physical-long')
        for mode in ('off', 'on'):
            command = command_for(*arguments, mode, 32, Path('/timing.json'),
                                  projection_preview_admission=True)
            self.assertEqual('--diagnostic-projection-preview-admission' in command,
                             mode == 'on')
            for flag in ('--diagnostic-native-partial-cues',
                         '--diagnostic-cue-free-lane-reassignment',
                         '--diagnostic-skip-empty-fine-reset'):
                self.assertNotIn(flag, command)
            self.assertIn('--diagnostic-core-timing', command)
            self.assertIn('--label-details', command)
            if mode == 'off':
                self.assertEqual(command, command_for(*arguments, mode, 32, Path('/timing.json')))

    def test_midi_capture_cannot_instrument_timing_or_buffer_comparison_runs(self):
        arguments = (Path('/replay'), Path('/corpus'), 'physical-long', 'off')
        command = command_for(*arguments, 512, Path('/unused.json'), midi_trace=Path('/midi.tsv'))
        self.assertIn('--midi-event-trace', command)
        self.assertNotIn('--diagnostic-core-timing', command)
        for block in (32, 1024):
            with self.subTest(block=block), self.assertRaisesRegex(ValueError, 'untimed'):
                command_for(*arguments, block, Path('/timing.json'), midi_trace=Path('/midi.tsv'))

    def test_collision_policy_is_isolated_and_cannot_mix_with_preview(self):
        arguments = (Path('/replay'), Path('/corpus'), 'physical-long')
        for mode in ('off', 'on'):
            command = command_for(*arguments, mode, 32, Path('/timing.json'),
                                  spectral_lane_collision=True)
            diagnostic = [flag for flag in command if flag.startswith('--diagnostic-')]
            self.assertEqual(diagnostic, ['--diagnostic-core-timing'] +
                (['--diagnostic-spectral-lane-collision'] if mode == 'on' else []))
        with self.assertRaisesRegex(ValueError, 'one isolated policy'):
            command_for(*arguments, 'on', 32, Path('/timing.json'),
                        spectral_lane_collision=True, projection_preview_admission=True)

    def test_fail_closed_timing_allocation_and_scored_identity(self):
        replay = {'output': {'fingerprint': '0123456789abcdef'}}
        timing = dict(schema='m3_replay_core_timing_v1', fingerprint_identical=True,
                      fingerprint='0123456789abcdef', block_samples=32, sample_rate=96000,
                      allocation_guard=True, cpp_allocations=0, cpp_frees=0,
                      c_allocations=0, c_frees=0, p99_ns=166666, maximum_ns=333333,
                      deadline_overruns=0, measurement_scope=MEASUREMENT_SCOPE)
        self.assertTrue(all(timing_gates(timing, replay, 32).values()))
        for key in ('p99_ns', 'maximum_ns', 'deadline_overruns'):
            changed = dict(timing, **{key: timing[key] + 1})
            self.assertFalse(timing_gates(changed, replay, 32)['timing_pass'])
        for key in ('cpp_allocations', 'cpp_frees', 'c_allocations', 'c_frees'):
            changed = dict(timing, **{key: 1})
            self.assertFalse(timing_gates(changed, replay, 32)['zero_processing_allocations'])
        self.assertFalse(timing_gates(dict(timing, fingerprint='bad'), replay, 32)['timing_pass'])
        self.assertFalse(timing_gates({}, replay, 32)['zero_processing_allocations'])
        self.assertIsNone(timing_gates(dict(timing, block_samples=512), replay, 512)['timing_pass'])
        for marker in ({'timing_diagnostic_only': True}, {'allocation_trace': {}},
                       {'thread_cpu': {}}, {'stage_cpu': {}}, {'measurement_scope': None},
                       {'measurement_scope':
                        'detector_and_optional_cues_without_offline_frequency_observer'}):
            gates = timing_gates(dict(timing, **marker), replay, 32)
            self.assertTrue(gates['timed_scored_identity'])
            self.assertFalse(gates['zero_processing_allocations'])
            self.assertFalse(gates['timing_pass'])

    def mocked_corpus(self, *, slow_mode=None, policy='cues', capture=False,
                      raw_delta=-4, raw_regression=None, reference_drift=None,
                      trace_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, manifest = root / 'results', root / 'manifest.json'
            names = ('physical-long.wav', 'physical-long.tsv',
                     'calibration.m3cb', 'templates.tsv')
            manifest.write_text(json.dumps({'files': {
                name: {'sha256': 'hash'} for name in names}}))
            parsed = {'output': {'fingerprint': 'unchanged'},
                      'exact_matches_by_string_count': {}}
            reference = root / 'reference.json'
            row = dict(parsed, tsv_sha256='hash')
            if reference_drift == 'hash':
                row['tsv_sha256'] = 'different'
            elif reference_drift == 'output':
                row['output'] = {'fingerprint': 'different'}
            reference.write_text(json.dumps({'datasets': {
                'physical-long': {'runs': {'off-32': row}}}}))
            flag = {'cues': '--diagnostic-native-partial-cues',
                    'preview': '--diagnostic-projection-preview-admission',
                    'collision': '--diagnostic-spectral-lane-collision'}[policy]

            def execute(command, **kwargs):
                if '--diagnostic-core-timing' in command:
                    mode = 'on' if flag in command else 'off'
                    timing = dict(schema='m3_replay_core_timing_v1',
                                  measurement_scope=MEASUREMENT_SCOPE,
                                  fingerprint_identical=True, fingerprint='unchanged',
                                  block_samples=32, sample_rate=96000,
                                  allocation_guard=True, cpp_allocations=0, cpp_frees=0,
                                  c_allocations=0, c_frees=0, p99_ns=100000,
                                  maximum_ns=333334 if mode == slow_mode else 200000,
                                  deadline_overruns=1 if mode == slow_mode else 0)
                    Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(
                        json.dumps(timing))

            def analyze(midi, replay, *, include_raw_conflicts=False):
                if trace_failure:
                    raise ValueError('MIDI event capture differs from replay transition count')
                result = {'coverage_valid': False}
                if include_raw_conflicts:
                    counts = dict.fromkeys(CONFLICT_FIELDS, 0)
                    counts['cross_pitch_on_before_release'] = 7
                    if '-on-' in midi.name:
                        counts['cross_pitch_on_before_release'] += raw_delta
                        if raw_regression is not None:
                            counts[raw_regression] += 1
                    result['raw_midi'] = dict(counts=counts, raw_note_ons_open_at_eof=[{}])
                return result

            argv = ['recovery', '--binary', str(root / 'replay'), '--corpus', str(root),
                    '--manifest', str(manifest), '--output', str(output)]
            if policy == 'preview':
                argv.append('--projection-preview-admission')
            elif policy == 'collision':
                argv.extend(('--spectral-lane-collision', '--off-reference-report', str(reference)))
            if capture:
                argv.append('--capture-midi-lifecycle')
            comparison = dict(gate_pass=True, output_bit_identical=True, changed_labels=[])
            with patch('sys.argv', argv), \
                 patch('tools.portable_corpus_replay.DATASETS', ('physical-long',)), \
                 patch('tools.portable_corpus_replay.digest', return_value='hash'), \
                 patch('tools.portable_corpus_replay.subprocess.run', side_effect=execute), \
                 patch('tools.portable_corpus_replay.read_replay', return_value=parsed), \
                 patch('tools.portable_corpus_replay.compare_replays', return_value=comparison), \
                 patch('tools.portable_corpus_replay.analyze_trace', side_effect=analyze) as lifecycle, \
                 patch('builtins.print'):
                if reference_drift or trace_failure:
                    with self.assertRaises(ValueError):
                        main()
                else:
                    main()
            return json.loads((output / 'report.json').read_text()), lifecycle.call_count

    def test_corpus_requires_both_modes_to_meet_timing_limits(self):
        for slow_mode, policy, capture in product((None, 'off', 'on'),
                                                 ('cues', 'preview', 'collision'), (False, True)):
            with self.subTest(slow_mode=slow_mode, policy=policy, capture=capture):
                report, lifecycle_calls = self.mocked_corpus(slow_mode=slow_mode,
                                                            policy=policy, capture=capture)
                self.assertEqual(report['state'], 'completed')
                dataset = report['datasets']['physical-long']
                self.assertEqual(len(dataset['runs']), 6)
                self.assertTrue(dataset['recovery_safety_pass'])
                self.assertEqual(dataset['native_gate_pass'], slow_mode is None)
                self.assertEqual(report['native_gates_passed'], int(slow_mode is None))
                self.assertFalse(report['promotion_accepted'])
                self.assertFalse(report['installed_output_changed'])
                capture_enabled = capture or policy == 'collision'
                self.assertEqual(lifecycle_calls, 2 if capture_enabled else 0)
                self.assertEqual(report['midi_lifecycle_capture']['alters_acceptance_gates'],
                                 policy == 'collision')
                for key, run in dataset['runs'].items():
                    expected = capture_enabled and key.endswith('-512')
                    self.assertEqual('--midi-event-trace' in run['command'], expected)
                    self.assertEqual('midi_lifecycle' in run, expected)
                    if expected:
                        self.assertFalse(run['midi_lifecycle']['coverage_valid'])
                if policy == 'preview':
                    self.assertEqual(report['schema'], 'm3_portable_projection_preview_corpus_v1')
                    self.assertEqual(report['trial_revision'], 'full_physical_assignment_context')
                    self.assertEqual(report['on_flags'], ['--diagnostic-projection-preview-admission'])
                elif policy == 'collision':
                    self.assertEqual(report['schema'], 'm3_portable_spectral_lane_collision_corpus_v1')
                    self.assertEqual(report['on_flags'], ['--diagnostic-spectral-lane-collision'])
                    self.assertTrue(report['off_references_bit_identical'])
                    self.assertTrue(dataset['raw_midi_no_regression'])
                    self.assertTrue(report['raw_midi_comparison']['conflicts_reduced'])
                    self.assertEqual(report['full_corpus_screen_pass'], slow_mode is None)
                else:
                    self.assertEqual(report['schema'], 'm3_portable_corpus_recovery_v1')
                    self.assertNotIn('trial_revision', report)

    def test_collision_corpus_rejects_each_raw_error_regression_and_parity_alone(self):
        for field in CONFLICT_FIELDS:
            with self.subTest(field=field):
                report, _ = self.mocked_corpus(policy='collision', raw_regression=field,
                                              raw_delta=0 if field == CONFLICT_FIELDS[0] else -4)
                self.assertFalse(report['full_corpus_screen_pass'])
                self.assertFalse(report['raw_midi_comparison']['no_regression'])
                self.assertEqual(report['stopped_on_regression'], 'physical-long')
                self.assertFalse(report['datasets']['physical-long']['recovery_safety_pass'])
                self.assertEqual(report['decision'], 'rejected')
        report, _ = self.mocked_corpus(policy='collision', raw_delta=0)
        self.assertTrue(report['raw_midi_comparison']['no_regression'])
        self.assertFalse(report['raw_midi_comparison']['conflicts_reduced'])
        self.assertFalse(report['full_corpus_screen_pass'])

    def test_collision_corpus_rejects_off_drift_and_incomplete_midi(self):
        for drift in ('output', 'hash'):
            with self.subTest(drift=drift):
                report, _ = self.mocked_corpus(policy='collision', reference_drift=drift)
                self.assertEqual(report['state'], 'failed')
                self.assertIn('OFF reference differs', report['error'])
                self.assertFalse(report['full_corpus_screen_pass'])
        report, _ = self.mocked_corpus(policy='collision', trace_failure=True)
        self.assertEqual(report['state'], 'failed')
        self.assertIn('transition count', report['error'])
        self.assertFalse(report['full_corpus_screen_pass'])

    def test_failed_eleventh_input_preserves_ten_references_and_stderr(self):
        self.check_failed_recovery(subprocess.CalledProcessError(1, ['replay']))

    def test_unexpected_failure_also_leaves_a_final_report(self):
        self.check_failed_recovery(RuntimeError('unexpected parser failure'))

    def check_failed_recovery(self, failure):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'results'
            manifest = root / 'manifest.json'
            names = {'calibration.m3cb', 'templates.tsv'} | {
                name + suffix for name in DATASETS for suffix in ('.wav', '.tsv')}
            manifest.write_text(json.dumps({'files': {name: {'sha256': 'hash'} for name in names}}))
            calls = []

            def replay(command, **kwargs):
                calls.append(command)
                if len(calls) == 11:
                    kwargs['stderr'].write('m3_replay: unsupported_wave\n')
                    raise failure
                return subprocess.CompletedProcess(command, 0)

            argv = ['recovery', '--binary', str(root / 'replay'), '--corpus', str(root),
                    '--manifest', str(manifest), '--output', str(output)]
            parsed = {'output': {'fingerprint': 'unchanged'}, 'exact_matches_by_string_count': {}}
            with patch('sys.argv', argv), patch('tools.portable_corpus_replay.digest', return_value='hash'), \
                 patch('tools.portable_corpus_replay.subprocess.run', side_effect=replay), \
                 patch('tools.portable_corpus_replay.read_replay', return_value=parsed), patch('builtins.print'):
                with self.assertRaises(type(failure)):
                    main()
            report = json.loads((output / 'report.json').read_text())
            self.assertEqual(report['state'], 'failed')
            self.assertTrue(report['final'])
            self.assertEqual(report['off_references'], 10)
            self.assertEqual(report['on_references'], 0)
            self.assertEqual(report['failure']['dataset'], 'extended-highmid')
            self.assertIn('unsupported_wave', report['failure']['stderr_tail'])
            self.assertFalse(report['promotion_accepted'])
            self.assertFalse(report['installed_output_changed'])


if __name__ == '__main__':
    unittest.main()
