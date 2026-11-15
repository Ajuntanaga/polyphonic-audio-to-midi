from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_calibrated_midi_retention_corpus as corpus
from tools.portable_corpus_replay import MEASUREMENT_SCOPE


class CalibratedRetentionCorpusTests(unittest.TestCase):
    POLICY = 'calibrated-midi-retention'
    DATASET = 'ordinary'
    LABEL_OFFSET = 0
    TRIAL = corpus.TRIAL

    @property
    def conditions(self):
        return corpus.POLICIES[self.POLICY]['conditions']

    def exercise(self, *, change=None, reference_drift=None, failure=False,
                 input_drift=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / 'inputs'
            inputs.mkdir()
            binary = root / 'replay'
            binary.write_text('fixture binary, never executed')
            files = {}
            for name in ('calibration.m3cb', 'templates.tsv', self.DATASET + '.wav', self.DATASET + '.tsv'):
                (inputs / name).write_text(name)
                files[name] = dict(sha256=corpus.digest(inputs / name))
            source = dict(input_release='release', input_bundle_sha256='bundle',
                          original_input_manifest_sha256='manifest')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(dict(source=source, files=files)))
            if input_drift:
                (inputs / (self.DATASET + '.wav')).write_text('changed')
            labels = [dict(label_index=i + self.LABEL_OFFSET, midi_note=37 + i + self.LABEL_OFFSET, string_mask=1 << i,
                           start_sample=i * 64, end_sample=(i + 1) * 64,
                           calibration_pass=0, labeled=10, matched=6)
                      for i in range(2)]
            base_output = dict(labeled=20, matched=12, false_wrong_note_voices=1,
                false_wrong_string_voices=2, false_gap_voices=3, false_positive_voices=6,
                fingerprint='0123456789abcdef')
            base_replay = dict(output=base_output, labels=labels,
                               exact_matches_by_string_count={'1': dict(labeled=20, matched=12)})

            def mode_of(path):
                return next(mode for mode, _ in self.conditions if mode in str(path))

            def parsed(path):
                mode = mode_of(path)
                block = int(path.stem.rsplit('-', 1)[1])
                result = deepcopy(base_replay)
                if mode == self.TRIAL:
                    result['output']['fingerprint'] = 'fedcba9876543210'
                if change:
                    change('replay', mode, block, result)
                return result

            def lifecycle(path, tsv, replay):
                mode = mode_of(path)
                rows = [dict({key: label[key] for key in corpus.LABEL_IDENTITY},
                             exact_held_samples=5, note_ons_inside_label=10) for label in labels]
                if mode == self.TRIAL:
                    rows[0].update(exact_held_samples=8, note_ons_inside_label=9)
                result = dict(coverage_valid=True, labels=rows, sample_count=128, sample_rate=96000,
                    output_safety=dict(valid=True, counts=dict.fromkeys(corpus.OUTPUT_SAFETY_FIELDS, 5)),
                    raw_midi=dict(counts=dict.fromkeys(corpus.CONFLICT_FIELDS, 0)))
                if change:
                    change('lifecycle', mode, 512, result)
                result['exact_held_samples'] = sum(row['exact_held_samples'] for row in rows)
                return result

            references = dict(schema=corpus.REFERENCE_SCHEMA, settings=corpus.SETTINGS,
                block_samples=512, reference_flags={m: list(f) for m, f in self.conditions[:2]},
                source=source, anchor_report_sha256='saved-report', datasets={self.DATASET: {}})
            for mode, _ in self.conditions[:2]:
                references['datasets'][self.DATASET][mode] = dict(output=deepcopy(base_output),
                    exact_matches_by_string_count=base_replay['exact_matches_by_string_count'],
                    tsv_sha256=hashlib.sha256(mode.encode()).hexdigest(), midi_trace_sha256=mode,
                    sample_count=128, sample_rate=96000)
            if reference_drift:
                mode, field = reference_drift
                references['datasets'][self.DATASET][mode][field] = 'different'
            reference_path = root / 'references.json'
            reference_path.write_text(json.dumps(references))
            commands = []

            def native(command, stdout, stderr, **kwargs):
                commands.append(command)
                mode = mode_of(stdout.name)
                block = int(command[command.index('--block') + 1])
                if failure:
                    stderr.write('named native fixture failure')
                    raise subprocess.CalledProcessError(1, command)
                stdout.write(mode)
                for flag in ('--midi-event-trace', '--outcome-trace'):
                    if flag in command:
                        Path(command[command.index(flag) + 1]).write_text('fixture')
                if block == 32:
                    self.assertNotIn('--midi-event-trace', command)
                    self.assertNotIn('--outcome-trace', command)
                    timing = dict(schema='m3_replay_core_timing_v1', fingerprint_identical=True,
                        fingerprint=parsed(Path(stdout.name))['output']['fingerprint'],
                        block_samples=32, sample_rate=96000, measurement_scope=MEASUREMENT_SCOPE,
                        allocation_guard=True, cpp_allocations=0, cpp_frees=0,
                        c_allocations=0, c_frees=0, p99_ns=166666, maximum_ns=333333,
                        deadline_overruns=0)
                    if change:
                        change('timing', mode, block, timing)
                    Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(json.dumps(timing))
                self.assertEqual('--diagnostic-' + self.POLICY in command, mode == self.TRIAL)
                self.assertEqual('--diagnostic-spectral-lane-collision' in command, mode != corpus.OFF)

            def compressed(path, **kwargs):
                result = dict(raw_sha256=mode_of(path) if '-midi.tsv' in path.name else 'same-outcomes')
                if change:
                    change('trace', mode_of(path), 512, result)
                return result

            output = root / 'output'
            with (patch.object(corpus, 'DATASETS', (self.DATASET,)),
                  patch.object(corpus.subprocess, 'run', side_effect=native),
                  patch.object(corpus, 'read_replay', side_effect=parsed),
                  patch.object(corpus, 'analyze_midi', side_effect=lifecycle),
                  patch.object(corpus, 'outcome_window'),
                  patch.object(corpus, 'compress_trace_window', side_effect=compressed)):
                if reference_drift or failure or input_drift:
                    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        corpus.run(binary, inputs, manifest, reference_path, output, policy=self.POLICY)
                else:
                    corpus.run(binary, inputs, manifest, reference_path, output, policy=self.POLICY)
            report = json.loads((output / 'report.json').read_text())
            self.assertTrue(report['final'])
            self.assertFalse(report['promotion_accepted'])
            self.assertFalse(report['installed_output_changed'])
            return report, commands

    def test_three_modes_pass_with_zero_conflicts_and_changed_trial_fingerprint(self):
        report, commands = self.exercise()
        self.assertEqual(len(commands), 9)
        self.assertTrue(report['reference_identity_pass'])
        self.assertTrue(report['corpus_note_safety_pass'])
        self.assertTrue(report['full_corpus_screen_pass'])
        self.assertEqual(report['improved_hold_and_attack_labels'], 1)
        self.assertEqual(report['native_datasets_passed'], 1)
        self.assertEqual(report['native_datasets_passed_by_mode'],
                         {mode: 1 for mode, _ in self.conditions})
        self.assertEqual(report['policy_name'], self.POLICY)
        self.assertEqual(report['inference_identity_required'],
                         self.POLICY == 'calibrated-midi-retention')

    def test_saved_reference_drift_stops_before_trial(self):
        for mode in (corpus.OFF, corpus.CURRENT):
            for field in ('tsv_sha256', 'midi_trace_sha256', 'output',
                          'exact_matches_by_string_count', 'sample_count', 'sample_rate'):
                with self.subTest(mode=mode, field=field):
                    report, commands = self.exercise(reference_drift=(mode, field))
                    self.assertEqual(len(commands), 1 if mode == corpus.OFF else 2)
                    self.assertFalse(report['full_corpus_screen_pass'])
                    self.assertIn('reference identity drift', report['error'])

    def test_one_held_loss_rejects_despite_positive_aggregate(self):
        def change(kind, mode, block, row):
            if kind == 'lifecycle' and mode == self.TRIAL:
                row['labels'][1]['exact_held_samples'] -= 1
        report, commands = self.exercise(change=change)
        comparison = report['datasets'][self.DATASET]['comparison']
        self.assertGreater(comparison['exact_held_samples_delta'], 0)
        self.assertEqual(len(comparison['held_losses']), 1)
        self.assertFalse(report['corpus_note_safety_pass'])
        self.assertEqual(len(commands), 3)

    def test_each_false_duration_onset_and_conflict_growth_rejects(self):
        for group, fields in (('output_safety', corpus.OUTPUT_SAFETY_FIELDS),
                              ('raw_midi', corpus.CONFLICT_FIELDS)):
            for field in fields:
                def change(kind, mode, block, row):
                    if kind == 'lifecycle' and mode == self.TRIAL:
                        row[group]['counts'][field] += 1
                with self.subTest(field=field):
                    report, commands = self.exercise(change=change)
                    self.assertFalse(report['corpus_note_safety_pass'])
                    self.assertEqual(len(commands), 3)

    def test_outcome_or_snapshot_inference_change_rejects(self):
        for selected in ('trace', 'replay'):
            def change(kind, mode, block, row):
                if kind == selected and mode == self.TRIAL:
                    if selected == 'trace':
                        row['raw_sha256'] = 'changed'
                    else:
                        row['output']['false_wrong_note_voices'] += 1
            with self.subTest(selected=selected):
                report, _ = self.exercise(change=change)
                self.assertFalse(report['datasets'][self.DATASET]['comparison']['inference_bit_identical'])
                self.assertFalse(report['full_corpus_screen_pass'])

    def test_timing_and_allocations_gate_each_mode_separately(self):
        for selected_mode, _ in self.conditions:
            for field in ('p99_ns', 'maximum_ns', 'deadline_overruns', 'cpp_allocations',
                          'cpp_frees', 'c_allocations', 'c_frees'):
                def change(kind, mode, block, row):
                    if kind == 'timing' and mode == selected_mode:
                        row[field] += 1
                with self.subTest(mode=selected_mode, field=field):
                    report, commands = self.exercise(change=change)
                    self.assertTrue(report['corpus_note_safety_pass'])
                    self.assertFalse(report['full_corpus_screen_pass'])
                    self.assertEqual(len(commands), 9)
                    self.assertEqual(report['native_datasets_passed_by_mode'],
                                     {mode: int(mode != selected_mode)
                                      for mode, _ in self.conditions})

    def test_buffer_identity_required_for_each_untraced_mode_and_block(self):
        for selected_mode, _ in self.conditions:
            for selected_block in (32, 1024):
                def change(kind, mode, block, row):
                    if kind == 'replay' and mode == selected_mode and block == selected_block:
                        row['output']['fingerprint'] = 'a' * 16
                with self.subTest(mode=selected_mode, block=selected_block):
                    report, _ = self.exercise(change=change)
                    self.assertFalse(report['full_corpus_screen_pass'])
                    self.assertFalse(report['datasets'][self.DATASET]['buffer_pass'])

    def test_parity_without_hold_and_attack_improvement_does_not_qualify(self):
        def change(kind, mode, block, row):
            if kind == 'lifecycle' and mode == self.TRIAL:
                row['labels'][0].update(exact_held_samples=5, note_ons_inside_label=10)
        report, _ = self.exercise(change=change)
        self.assertTrue(report['datasets'][self.DATASET]['note_safety_pass'])
        self.assertFalse(report['corpus_note_safety_pass'])

    def test_changed_inputs_and_native_failure_keep_final_failure_report(self):
        report, commands = self.exercise(input_drift=True)
        self.assertFalse(commands)
        self.assertIn('Input hash mismatch', report['error'])
        report, commands = self.exercise(failure=True)
        self.assertEqual(len(commands), 1)
        self.assertTrue(report['failure_stderr'].endswith('.stderr'))
        self.assertEqual(report['failure_stderr_tail'], 'named native fixture failure')



class QualifiedTierRetentionCorpusTests(CalibratedRetentionCorpusTests):
    POLICY = 'qualified-tier-retention'
    DATASET = 'physical-long'
    LABEL_OFFSET = 3
    TRIAL = 'qualified-tier-retention-on'

    def test_outcome_or_snapshot_inference_change_rejects(self):
        # This policy changes assignments, so safe gains are allowed; false
        # snapshot growth must still reject even when inference identity is off.
        for field in ('false_wrong_note_voices', 'false_wrong_string_voices',
                      'false_gap_voices', 'false_positive_voices'):
            def change(kind, mode, block, row):
                if kind == 'replay' and mode == self.TRIAL:
                    row['output'][field] += 1
            with self.subTest(field=field):
                report, commands = self.exercise(change=change)
                self.assertFalse(report['full_corpus_screen_pass'])
                self.assertEqual(len(commands), 3)

    def test_safe_snapshot_and_outcome_gain_keeps_all_other_gates(self):
        def change(kind, mode, block, row):
            if mode != self.TRIAL:
                return
            if kind == 'trace':
                row['raw_sha256'] = 'changed-outcome'
            elif kind == 'replay':
                row['output']['matched'] += 1
                row['labels'][0]['matched'] += 1
                row['exact_matches_by_string_count']['1']['matched'] += 1
        report, commands = self.exercise(change=change)
        self.assertFalse(report['datasets'][self.DATASET]['comparison']['inference_bit_identical'])
        self.assertTrue(report['required_target_hold_and_attack_improved'])
        self.assertTrue(report['full_corpus_screen_pass'])
        self.assertEqual(len(commands), 9)

    def test_one_passage_loss_rejects_despite_positive_frame_aggregate(self):
        def change(kind, mode, block, row):
            if kind == 'replay' and mode == self.TRIAL:
                row['labels'][0]['matched'] += 2
                row['labels'][1]['matched'] -= 1
                row['output']['matched'] += 1
        report, commands = self.exercise(change=change)
        comparison = report['datasets'][self.DATASET]['comparison']['snapshot']
        self.assertEqual(comparison['delta']['matched'], 1)
        self.assertEqual(comparison['lost_labels'], [4])
        self.assertFalse(report['corpus_note_safety_pass'])
        self.assertEqual(len(commands), 3)

    def test_unrelated_hold_gain_cannot_replace_required_physical_target(self):
        def change(kind, mode, block, row):
            if kind == 'lifecycle' and mode == self.TRIAL:
                row['labels'][0].update(exact_held_samples=5, note_ons_inside_label=10)
                row['labels'][1].update(exact_held_samples=8, note_ons_inside_label=9)
        report, _ = self.exercise(change=change)
        self.assertEqual(report['improved_hold_and_attack_labels'], 1)
        self.assertFalse(report['required_target_hold_and_attack_improved'])
        self.assertFalse(report['corpus_note_safety_pass'])

if __name__ == '__main__':
    unittest.main()
