from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.portable_corpus_replay import command_for, timing_gates, main
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

    def test_fail_closed_timing_allocation_and_scored_identity(self):
        replay = {'output': {'fingerprint': '0123456789abcdef'}}
        timing = dict(schema='m3_replay_core_timing_v1', fingerprint_identical=True,
                      fingerprint='0123456789abcdef', block_samples=32, sample_rate=96000,
                      allocation_guard=True, cpp_allocations=0, cpp_frees=0,
                      c_allocations=0, c_frees=0, p99_ns=166666, maximum_ns=333333,
                      deadline_overruns=0)
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
                       {'thread_cpu': {}}):
            gates = timing_gates(dict(timing, **marker), replay, 32)
            self.assertTrue(gates['timed_scored_identity'])
            self.assertFalse(gates['zero_processing_allocations'])
            self.assertFalse(gates['timing_pass'])

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
