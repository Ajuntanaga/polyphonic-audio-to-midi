import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.portable_controlled_replay import run, run_timing_diagnosis, validate_labels
from tools.portable_corpus_replay import MEASUREMENT_SCOPE, SETTINGS
from tools.recover_controlled_inputs import float_crop


class ControlledRecoveryTests(unittest.TestCase):
    def test_crop_seeks_past_metadata_and_preserves_float_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.wav'
            fmt = struct.pack('<HHIIHH', 3, 1, 96000, 384000, 4, 32)
            samples = struct.pack('<4f', -.7, .1234567, -.00000001, .2)
            body = (b'WAVEfmt ' + struct.pack('<I', 18) + fmt + b'\0\0'
                    + b'JUNK' + struct.pack('<I', 3) + b'abc\0'
                    + b'data' + struct.pack('<I', len(samples)) + samples)
            path.write_bytes(b'RIFF' + struct.pack('<I', len(body)) + body)
            raw, wave = float_crop(path, 1, 3, 96000)
            self.assertEqual(raw, samples[4:12])
            self.assertEqual(wave[44:], raw)
            self.assertEqual(len(wave), 52)
            with self.assertRaises(ValueError):
                float_crop(path, 0, 5, 96000)
            broken = bytearray(path.read_bytes())
            struct.pack_into('<H', broken, 22, 2)
            path.write_bytes(broken)
            with self.assertRaises(ValueError):
                float_crop(path, 0, 2, 96000)

    def exercise(self, *, gain=1, extra_false=False, timing_failure=False, native_error=False):
        label = dict(start_sample=64, end_sample=256, midi_note=36, string_mask=1, calibration_pass=2)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, manifest, reference = (root / name for name in ('binary', 'manifest', 'reference'))
            binary.write_bytes(b'fixture')
            manifest.write_text(json.dumps(dict(source={'commit': 'fixture'}, files={'a': {}})))
            reference.write_text('{}')
            inputs = {'nearby_0dB': dict(has_target=True, labels=[label]),
                      'silence': dict(has_target=False, labels=[])}
            calls = []

            def execute(command, **kwargs):
                name = Path(command[command.index('--wav') + 1]).stem
                mode = 'on' if '--diagnostic-native-partial-cues' in command else 'off'
                block = int(command[command.index('--block') + 1])
                calls.append((name, mode, block))
                if native_error:
                    kwargs['stderr'].write('fixture native failure\n')
                    raise subprocess.CalledProcessError(1, command)
                matched = (1 + (gain if mode == 'on' else 0)) if name != 'silence' else 0
                false = int(extra_false and name == 'silence' and mode == 'on')
                fingerprint = hashlib.sha256(f'{name}-{matched}-{false}'.encode()).hexdigest()[:16]
                kwargs['stdout'].write('labeled\tmatched\tfalse_wrong_note_voices\tfalse_wrong_string_voices'
                    '\tfalse_gap_voices\tfalse_positive_voices\tfingerprint\n'
                    f'{3 if name != "silence" else 0}\t{matched}\t0\t0\t{false}\t{false}\t{fingerprint}\n'
                    'label_index\tstart_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\tlabeled\tmatched\n')
                if name != 'silence':
                    kwargs['stdout'].write(f'0\t64\t256\t36\t1\t2\t3\t{matched}\n')
                if block == 32:
                    timing = dict(schema='m3_replay_core_timing_v1', measurement_scope=MEASUREMENT_SCOPE,
                        fingerprint_identical=True, fingerprint=fingerprint, block_samples=32, sample_rate=96000,
                        allocation_guard=True, cpp_allocations=0, cpp_frees=0, c_allocations=0, c_frees=0,
                        p99_ns=100000, maximum_ns=400000 if timing_failure else 200000, deadline_overruns=0)
                    Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(json.dumps(timing))

            passed, error = None, None
            output = root / 'output'
            with patch('tools.portable_controlled_replay.prepare_cases', return_value=inputs), \
                 patch('tools.portable_controlled_replay.subprocess.run', side_effect=execute):
                try:
                    passed = run(binary, root, manifest, reference, output, 10)
                except subprocess.CalledProcessError as caught:
                    error = caught
            report = json.loads((output / 'report.json').read_text())
            self.assertTrue(report['final'])
            self.assertFalse(report['promotion_accepted'])
            self.assertFalse(report['installed_output_changed'])
            stderr = (output / report['current_stderr_file']).read_text()
            return passed, report, calls, error, stderr

    def test_safe_target_gain_requires_both_modes_and_buffer_timing_gates(self):
        passed, report, calls, error, _ = self.exercise()
        self.assertTrue(passed)
        self.assertIsNone(error)
        self.assertEqual(len(calls), 12)
        self.assertEqual(report['accuracy_screen']['nearby_target_gain'], 1)
        self.assertTrue(all(row['native_gate_pass'] for row in report['datasets'].values()))
        self.assertEqual(report['live_readiness'], 'not measured')

    def test_parity_or_source_only_false_gain_stops_before_timing(self):
        for kwargs in (dict(gain=0), dict(extra_false=True)):
            with self.subTest(kwargs=kwargs):
                passed, report, calls, _, _ = self.exercise(**kwargs)
                self.assertFalse(passed)
                self.assertTrue(report['collection_pass'])
                self.assertFalse(report['accuracy_screen']['pass_screen'])
                self.assertTrue(all(block == 512 for _, _, block in calls))

    def test_timing_failure_is_not_accepted_collection(self):
        passed, report, calls, _, _ = self.exercise(timing_failure=True)
        self.assertFalse(passed)
        self.assertTrue(report['collection_pass'])
        self.assertTrue(report['accuracy_screen']['pass_screen'])
        self.assertEqual(len(calls), 12)

    def test_native_failure_keeps_report_and_error_log(self):
        passed, report, calls, error, stderr = self.exercise(native_error=True)
        self.assertIsNone(passed)
        self.assertIsNotNone(error)
        self.assertEqual(report['state'], 'failed')
        self.assertEqual(len(calls), 1)
        self.assertEqual(stderr, 'fixture native failure\n')

    def test_label_loss_cannot_be_hidden_in_aggregate_gain(self):
        labels = [dict(label_index=i, start_sample=64, end_sample=256, midi_note=36+i,
                       string_mask=1, calibration_pass=2, labeled=3, matched=1) for i in range(2)]
        before = dict(labels=labels, output=dict(labeled=6, matched=2, false_wrong_note_voices=0,
            false_wrong_string_voices=0, false_gap_voices=0, false_positive_voices=0, fingerprint='a'))
        after = copy.deepcopy(before)
        after['labels'][0]['matched'], after['labels'][1]['matched'] = 0, 3
        after['output']['matched'] = 3
        self.assertFalse(compare_replays(before, after)['gate_pass'])
        with self.assertRaises(ValueError):
            validate_labels(before, [])


class ControlledTimingTests(unittest.TestCase):
    TSV = ('labeled\tmatched\tfalse_wrong_note_voices\tfalse_wrong_string_voices\t'
           'false_gap_voices\tfalse_positive_voices\tfingerprint\n'
           '3\t1\t0\t1\t2\t3\t0123456789abcdef\n'
           'label_index\tstart_sample\tend_sample\tmidi_note\tstring_mask\t'
           'calibration_pass\tlabeled\tmatched\n'
           '0\t64\t256\t36\t1\t2\t3\t1\n')

    def exercise(self, *, defect=None, resolution=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, manifest, reference, baseline = (
                root / name for name in ('binary', 'manifest', 'reference', 'baseline'))
            binary.write_bytes(b'fixture')
            manifest.write_text(json.dumps(dict(source={'commit': 'fixture'}, files={'a': {}})))
            reference.write_text('{}')
            retained = root / 'retained.tsv'
            retained.write_text(self.TSV)
            retained_hash = hashlib.sha256(retained.read_bytes()).hexdigest()
            output_counts = read_replay(retained)['output']
            pair = dict(replay_sha256={'off-32': retained_hash, 'on-32': retained_hash},
                        baseline_off=output_counts, current_on=output_counts, timing={})
            if defect in ('off-32', 'on-32'):
                del pair['replay_sha256'][defect]
            saved = dict(schema='m3_github_heldout_control_result_v1', final=True,
                         collection_pass=True, settings=SETTINGS, source={'commit': 'earlier'},
                         spectral_templates='disabled, matching historical controls',
                         reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                         controls={'octave_0dB': pair}, timing_limits={})
            if defect == 'input':
                saved['reference_sha256'] = 'different'
            if defect == 'settings':
                saved['settings'] = dict(SETTINGS, response=74)
            baseline.write_text(json.dumps(saved))
            label = dict(start_sample=64, end_sample=256, midi_note=36, string_mask=1, calibration_pass=2)
            inputs = {'octave_0dB': dict(labels=[label]), 'solo': dict(labels=[label])}
            calls = []

            def execute(command, **kwargs):
                mode = 'on' if '--diagnostic-native-partial-cues' in command else 'off'
                calls.append(mode)
                self.assertIn('--diagnostic-thread-cpu', command)
                self.assertNotIn('--spectral-shadow-templates', command)
                self.assertEqual('--diagnostic-cue-free-lane-reassignment' in command, mode == 'on')
                self.assertEqual(Path(command[command.index('--wav') + 1]).name, 'octave_0dB.wav')
                self.assertEqual(command[command.index('--block') + 1], '32')
                self.assertLessEqual(kwargs['timeout'], 180)
                if defect == 'native':
                    kwargs['stderr'].write('fixture native failure\n')
                    raise subprocess.CalledProcessError(1, command)
                kwargs['stdout'].write(self.TSV + ('\n' if defect == 'hash' else ''))
                timing = dict(schema='m3_replay_core_timing_v1', measurement_scope=MEASUREMENT_SCOPE,
                    fingerprint_identical=True, fingerprint='0123456789abcdef',
                    block_samples=32, sample_rate=96000, blocks=32, timing_diagnostic_only=True,
                    allocation_guard=True, cpp_allocations=0, cpp_frees=0, c_allocations=0, c_frees=0,
                    p99_ns=100000, maximum_ns=400000, deadline_overruns=1,
                    thread_cpu=dict(valid=True, block_resolution_pass=resolution,
                        phases=[dict(blocks=1, wall_deadline_overruns=int(i == 0)) for i in range(32)],
                        slowest_blocks=[dict(wall_ns=400000)]))
                if defect == 'cpu':
                    del timing['thread_cpu']
                if defect == 'scope':
                    timing['measurement_scope'] = 'old'
                if defect == 'fingerprint':
                    timing['fingerprint_identical'] = False
                Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(json.dumps(timing))

            passed, error = None, None
            output = root / 'output'
            with patch('tools.portable_controlled_replay.prepare_cases', return_value=inputs), \
                 patch('tools.portable_controlled_replay.subprocess.run', side_effect=execute):
                try:
                    passed = run_timing_diagnosis(binary, root, manifest, reference, baseline, output, 9999)
                except (ValueError, subprocess.CalledProcessError) as caught:
                    error = caught
            report = json.loads((output / 'report.json').read_text())
            self.assertTrue(report['final'])
            self.assertTrue(report['diagnostic_only'])
            self.assertFalse(report['promotion_accepted'])
            self.assertFalse(report['installed_output_changed'])
            self.assertFalse(report['native_gate_pass'])
            self.assertFalse(report['allocation_and_output_pass'])
            self.assertEqual(report['max_seconds'], 360)
            stderr = output / 'octave_0dB-off-32.stderr'
            return passed, report, calls, error, stderr.read_text() if stderr.exists() else None

    def test_only_saved_octave_pair_is_collected_without_native_acceptance(self):
        for resolution in (True, False):
            with self.subTest(resolution=resolution):
                passed, report, calls, error, _ = self.exercise(resolution=resolution)
                self.assertIsNone(error)
                self.assertTrue(passed)
                self.assertTrue(report['collection_pass'])
                self.assertEqual(calls, ['off', 'on'])
                self.assertTrue(all(row['recorded_reference_bit_identical'] for row in report['runs'].values()))
                self.assertEqual(report['cpu_block_statistics_usable'], resolution)
                self.assertEqual(report['acceptance'], 'not evaluated: diagnostic timing')

    def test_missing_pair_or_changed_reference_stops_before_native_calls(self):
        for defect in ('off-32', 'on-32', 'input', 'settings'):
            with self.subTest(defect=defect):
                _, report, calls, error, _ = self.exercise(defect=defect)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(calls, [])
                self.assertEqual(report['state'], 'failed')

    def test_changed_full_output_or_incomplete_timing_stops_before_on(self):
        for defect in ('hash', 'cpu', 'scope', 'fingerprint'):
            with self.subTest(defect=defect):
                _, report, calls, error, _ = self.exercise(defect=defect)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(calls, ['off'])
                self.assertEqual(report['state'], 'failed')

    def test_native_failure_is_retained_with_final_report(self):
        _, report, calls, error, stderr = self.exercise(defect='native')
        self.assertIsInstance(error, subprocess.CalledProcessError)
        self.assertEqual(calls, ['off'])
        self.assertEqual(report['state'], 'failed')
        self.assertEqual(stderr, 'fixture native failure\n')


if __name__ == '__main__':
    unittest.main()
