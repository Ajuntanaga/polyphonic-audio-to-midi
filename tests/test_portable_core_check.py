import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_assignment_trace import digest
from tools.portable_core_check import MEASUREMENT_SCOPE, run
from tools.portable_corpus_replay import SETTINGS


class CoreCheckTests(unittest.TestCase):
    TSV = (
        'labeled\tmatched\tfalse_wrong_note_voices\tfalse_wrong_string_voices\t'
        'false_gap_voices\tfalse_positive_voices\tfingerprint\n'
        '10\t8\t1\t0\t2\t3\t0123456789abcdef\n'
        'label_index\tstart_sample\tend_sample\tmidi_note\tstring_mask\t'
        'calibration_pass\tlabeled\tmatched\n'
        '0\t0\t960\t52\t7\t1\t10\t8\n')

    def exercise(self, change=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, manifest = root / 'binary', root / 'manifest.json'
            reference, output = root / 'reference.json', root / 'output'
            binary.write_text('not executed')
            manifest.write_text('{"source":{"provider":"github-actions"}}')
            retained = root / 'retained.tsv'
            retained.write_text(self.TSV)
            baseline = dict(read_replay(retained), tsv_sha256=digest(retained))
            reference.write_text(json.dumps(dict(settings=SETTINGS, source={}, datasets={
                'physical-long': {'runs': {'off-32': baseline, 'on-32': baseline}}})))
            modes = []

            def execute(command, **kwargs):
                mode = 'on' if '--diagnostic-native-partial-cues' in command else 'off'
                modes.append(mode)
                self.assertEqual('--diagnostic-cue-free-lane-reassignment' in command,
                                 mode == 'on')
                self.assertEqual(command[command.index('--block') + 1], '32')
                timing = dict(schema='m3_replay_core_timing_v1', sample_rate=96000,
                              block_samples=32, measurement_scope=MEASUREMENT_SCOPE,
                              fingerprint='0123456789abcdef', fingerprint_identical=True,
                              allocation_guard=True, cpp_allocations=0, cpp_frees=0,
                              c_allocations=0, c_frees=0, p99_ns=100000,
                              maximum_ns=200000, deadline_overruns=0)
                kwargs['stdout'].write(self.TSV)
                if change:
                    change(mode, command, timing, kwargs)
                Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(
                    json.dumps(timing))

            error = None
            passed = None
            with patch('tools.portable_core_check.verify_inputs'), \
                 patch('tools.portable_core_check.subprocess.run', side_effect=execute):
                try:
                    passed = run(binary, root, manifest, reference, output, 10)
                except (ValueError, subprocess.CalledProcessError) as caught:
                    error = caught
            report = json.loads((output / 'report.json').read_text())
            self.assertTrue(report['final'])
            self.assertFalse(report['promotion_accepted'])
            self.assertFalse(report['installed_output_changed'])
            stderr = (output / 'physical-long-off-32.stderr').read_text()
            return passed, report, error, modes, stderr

    def test_pair_preserves_reference_and_keeps_live_acceptance_separate(self):
        passed, report, error, modes, _ = self.exercise()
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertEqual(modes, ['off', 'on'])
        self.assertTrue(report['comparison']['gate_pass'])
        self.assertTrue(report['allocation_and_output_pass'])
        self.assertEqual(report['live_readiness'], 'not measured')

    def test_allocation_or_timing_failure_is_rejected_after_both_modes(self):
        for key, value in (('cpp_allocations', 1), ('maximum_ns', 333334),
                           ('deadline_overruns', 1)):
            with self.subTest(key=key):
                def fail(mode, command, timing, kwargs):
                    if mode == 'on':
                        timing[key] = value
                passed, report, error, modes, _ = self.exercise(fail)
                self.assertIsNone(error)
                self.assertFalse(passed)
                self.assertEqual(modes, ['off', 'on'])
                self.assertEqual(report['state'], 'completed')
                self.assertEqual(report['acceptance'], 'rejected by core processing gates')

    def test_changed_file_or_unverified_measurement_stops_before_on(self):
        for defect in ('hash', 'scope', 'fingerprint'):
            with self.subTest(defect=defect):
                def fail(mode, command, timing, kwargs):
                    if defect == 'hash':
                        # Identical counts are insufficient when full output changed.
                        kwargs['stdout'].write('\n')
                    elif defect == 'scope':
                        del timing['measurement_scope']
                    else:
                        timing['fingerprint_identical'] = False
                passed, report, error, modes, _ = self.exercise(fail)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(report['state'], 'failed')
                self.assertEqual(modes, ['off'])

    def test_native_failure_retains_final_report_and_stderr(self):
        def fail(mode, command, timing, kwargs):
            kwargs['stderr'].write('replay failed\n')
            raise subprocess.CalledProcessError(1, command)
        passed, report, error, modes, stderr = self.exercise(fail)
        self.assertIsInstance(error, subprocess.CalledProcessError)
        self.assertEqual(report['state'], 'failed')
        self.assertEqual(modes, ['off'])
        self.assertEqual(stderr, 'replay failed\n')


if __name__ == '__main__':
    unittest.main()
