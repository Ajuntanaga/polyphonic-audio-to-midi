from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_calibrated_midi_retention_corpus as shared
from tools import portable_suppressed_adjacent_admission_trial as trial


class SuppressedAdjacentAdmissionTests(unittest.TestCase):
    policy = 'suppressed-adjacent-admission'

    def setUp(self):
        selected = trial.POLICIES[self.policy]
        self.trial_mode = selected['mode']
        self.flag = selected['flag']
        self.require_inference = selected.get('require_inference', False)
        self.screen_datasets = selected.get('datasets', trial.SCREEN_DATASETS)
        self.conditions = ((trial.OFF, ()), (trial.CURRENT, (trial.COLLISION,)),
                           (self.trial_mode, (trial.COLLISION, self.flag)))

    def exercise(self, *, change=None, drift=False, failure=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / 'inputs'
            inputs.mkdir()
            binary = root / 'replay'
            binary.write_text('fixture only; never executed')
            files = {}
            names = ['calibration.m3cb', 'templates.tsv'] + [
                name + suffix for name in self.screen_datasets for suffix in ('.wav', '.tsv')]
            for name in names:
                (inputs / name).write_text(name)
                files[name] = dict(sha256=trial.digest(inputs / name))
            source = dict(input_release='release', input_bundle_sha256='bundle',
                          original_input_manifest_sha256='manifest')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(dict(source=source, files=files)))
            labels = [dict(trial.TARGET, calibration_pass=0, labeled=10, matched=6),
                      dict(label_index=4, midi_note=52, string_mask=8,
                           start_sample=2932608, end_sample=5452800,
                           calibration_pass=0, labeled=10, matched=6)]
            base = dict(output=dict(labeled=20, matched=12, false_wrong_note_voices=1,
                false_wrong_string_voices=2, false_gap_voices=3, false_positive_voices=6,
                fingerprint='0123456789abcdef'), labels=labels,
                exact_matches_by_string_count={'3': dict(labeled=10, matched=6),
                                              '1': dict(labeled=10, matched=6)})

            def selection(path):
                name = next(name for name in self.screen_datasets if path.name.startswith(name + '-'))
                mode = next(mode for mode, _ in self.conditions if mode in path.name)
                return name, mode

            def parsed(path):
                name, mode = selection(path)
                row = deepcopy(base)
                if mode == self.trial_mode:
                    row['output']['fingerprint'] = 'fedcba9876543210'
                if change:
                    change('snapshot', name, mode, row)
                return row

            def lifecycle(path, tsv, replay):
                name, mode = selection(path)
                rows = [dict({key: label[key] for key in shared.LABEL_IDENTITY},
                             exact_held_samples=5, note_ons_inside_label=10)
                        for label in labels]
                if name == 'physical-long' and mode == self.trial_mode:
                    rows[0].update(exact_held_samples=8, note_ons_inside_label=9)
                row = dict(coverage_valid=True, labels=rows, sample_count=5646848,
                    sample_rate=96000,
                    output_safety=dict(valid=True, counts=dict.fromkeys(shared.OUTPUT_SAFETY_FIELDS, 5)),
                    raw_midi=dict(counts=dict.fromkeys(shared.CONFLICT_FIELDS, 0)))
                if change:
                    change('held', name, mode, row)
                row['exact_held_samples'] = sum(label['exact_held_samples'] for label in rows)
                return row

            references = dict(schema=shared.REFERENCE_SCHEMA, settings=shared.SETTINGS,
                block_samples=512, source=source, anchor_report_sha256='saved-report',
                reference_flags={m: list(f) for m, f in self.conditions[:2]}, datasets={})
            for name in self.screen_datasets:
                references['datasets'][name] = {}
                for mode, _ in self.conditions[:2]:
                    references['datasets'][name][mode] = dict(output=base['output'],
                        exact_matches_by_string_count=base['exact_matches_by_string_count'],
                        tsv_sha256=hashlib.sha256(mode.encode()).hexdigest(),
                        midi_trace_sha256=mode, sample_count=5646848, sample_rate=96000)
            if drift:
                references['datasets']['physical-long'][trial.CURRENT]['midi_trace_sha256'] = 'changed'
            reference_path = root / 'references.json'
            reference_path.write_text(json.dumps(references))
            commands = []

            def native(command, stdout, stderr, **kwargs):
                commands.append(command)
                _, mode = selection(Path(stdout.name))
                self.assertEqual(command[command.index('--block') + 1], '512')
                self.assertEqual('--outcome-trace' in command,
                                 self.require_inference and mode != trial.OFF)
                self.assertNotIn('--diagnostic-core-timing', command)
                self.assertEqual(self.flag in command, mode == self.trial_mode)
                for name, policy in trial.POLICIES.items():
                    if name != self.policy:
                        self.assertNotIn(policy['flag'], command)
                self.assertEqual(trial.COLLISION in command, mode != trial.OFF)
                if failure:
                    stderr.write('named replay fixture failure')
                    raise subprocess.CalledProcessError(1, command)
                stdout.write(mode)
                Path(command[command.index('--midi-event-trace') + 1]).write_text('fixture')
                if '--outcome-trace' in command:
                    Path(command[command.index('--outcome-trace') + 1]).write_text('fixture')

            def compress(path, **kwargs):
                name, mode = selection(path)
                is_outcome = path.name.endswith('-outcome.tsv')
                row = dict(raw_sha256='inference' if is_outcome else mode)
                if is_outcome and change:
                    change('outcome', name, mode, row)
                return row

            output = root / 'output'
            with (patch.object(shared, 'DATASETS', self.screen_datasets),
                  patch.object(trial.subprocess, 'run', side_effect=native),
                  patch.object(trial, 'read_replay', side_effect=parsed),
                  patch.object(trial, 'analyze_midi', side_effect=lifecycle),
                  patch.object(trial, 'outcome_window'),
                  patch.object(trial, 'compress_trace_window', side_effect=compress)):
                if drift or failure:
                    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        trial.run(binary, inputs, manifest, reference_path, output, policy=self.policy)
                else:
                    trial.run(binary, inputs, manifest, reference_path, output, policy=self.policy)
            report = json.loads((output / 'report.json').read_text())
            self.assertEqual(report['policy_name'], self.policy)
            self.assertEqual(report['schema'], trial.POLICIES[self.policy]['schema'])
            self.assertTrue(report['final'])
            self.assertFalse(report['promotion_accepted'])
            self.assertFalse(report['installed_output_changed'])
            self.assertEqual(report['native_timing'], 'not measured')
            return report, commands

    def test_target_gain_checks_declared_datasets_without_claiming_timing_or_promotion(self):
        report, commands = self.exercise()
        self.assertTrue(report['bounded_screen_pass'])
        self.assertEqual(report['declared_datasets'], list(self.screen_datasets))
        self.assertEqual(list(report['datasets']), list(self.screen_datasets))
        self.assertEqual(len(commands), 3 * len(self.screen_datasets))
        self.assertEqual(report['note_safety_datasets_passed'], len(self.screen_datasets))
        comparison = report['datasets']['physical-long']['comparison']
        self.assertEqual(comparison['inference_identity_required'], self.require_inference)
        self.assertIs(comparison['inference_bit_identical'], True if self.require_inference else None)

    def test_target_parity_stops_after_first_dataset(self):
        def change(kind, name, mode, row):
            if kind == 'held' and mode == self.trial_mode:
                row['labels'][0].update(exact_held_samples=5, note_ons_inside_label=10)
        report, commands = self.exercise(change=change)
        self.assertEqual(len(commands), 3)
        self.assertFalse(report['bounded_screen_pass'])
        self.assertEqual(report['state'], 'rejected')

    def test_one_held_loss_rejects_despite_target_gain(self):
        def change(kind, name, mode, row):
            if kind == 'held' and mode == self.trial_mode:
                row['labels'][1]['exact_held_samples'] -= 1
        report, commands = self.exercise(change=change)
        self.assertTrue(report['target_hold']['improved'])
        self.assertFalse(report['bounded_screen_pass'])
        self.assertEqual(len(commands), 3)

    def test_later_passage_loss_stops_before_remaining_datasets(self):
        def change(kind, name, mode, row):
            if kind == 'snapshot' and name == 'ordinary' and mode == self.trial_mode:
                row['labels'][1]['matched'] -= 1
        report, commands = self.exercise(change=change)
        self.assertFalse(report['bounded_screen_pass'])
        completed = self.screen_datasets.index('ordinary') + 1
        self.assertEqual(len(commands), 3 * completed)
        self.assertEqual(report['completed_datasets'], completed)

    def test_false_output_conflict_and_clock_regressions_reject(self):
        for group, fields in (('output_safety', shared.OUTPUT_SAFETY_FIELDS),
                              ('raw_midi', shared.CONFLICT_FIELDS),
                              ('clock', ('sample_count', 'sample_rate'))):
            for field in fields:
                def change(kind, name, mode, row):
                    if kind == 'held' and mode == self.trial_mode:
                        if group == 'clock':
                            row[field] += 1
                        else:
                            row[group]['counts'][field] += 1
                with self.subTest(field=field):
                    report, commands = self.exercise(change=change)
                    self.assertFalse(report['bounded_screen_pass'])
                    self.assertEqual(len(commands), 3)

    def test_saved_reference_drift_stops_before_trial(self):
        report, commands = self.exercise(drift=True)
        self.assertEqual(len(commands), 2)
        self.assertFalse(report['reference_identity_pass'])
        self.assertFalse(report['bounded_screen_pass'])

    def test_failure_retains_named_stderr_and_final_report(self):
        report, commands = self.exercise(failure=True)
        self.assertEqual(len(commands), 1)
        self.assertEqual(report['state'], 'failed')
        self.assertEqual(report['failure_stderr_tail'], 'named replay fixture failure')
        self.assertFalse(report['bounded_screen_pass'])


class FineSubsetConsensusTests(SuppressedAdjacentAdmissionTests):
    policy = 'fine-subset-consensus'


class QualifiedTierRetentionTests(SuppressedAdjacentAdmissionTests):
    policy = 'qualified-tier-retention'


class ContinuousTierRetentionTests(SuppressedAdjacentAdmissionTests):
    policy = 'continuous-tier-retention'

    def test_known_extended_middle_loss_stops_before_ordinary(self):
        def change(kind, name, mode, row):
            if kind == 'held' and name == 'extended-middle' and mode == self.trial_mode:
                row['labels'][1]['exact_held_samples'] -= 1
        report, commands = self.exercise(change=change)
        self.assertEqual(report['declared_datasets'], [
            'physical-long', 'extended-middle', 'ordinary', 'constructed', 'synthetic-four'])
        self.assertTrue(report['target_hold']['improved'])
        self.assertFalse(report['bounded_screen_pass'])
        self.assertEqual(report['state'], 'rejected')
        self.assertEqual(len(commands), 6)
        self.assertEqual(report['completed_datasets'], 2)
        self.assertNotIn('ordinary', report['datasets'])


class CompletionWindowRetentionTests(ContinuousTierRetentionTests):
    policy = 'completion-window-retention'


class CompletionMidiRetentionTests(ContinuousTierRetentionTests):
    policy = 'completion-midi-retention'

    def test_inference_outcome_drift_rejects_despite_target_gain(self):
        def change(kind, name, mode, row):
            if kind == 'outcome' and mode == self.trial_mode:
                row['raw_sha256'] = 'changed'
        report, commands = self.exercise(change=change)
        self.assertTrue(report['target_hold']['improved'])
        self.assertFalse(report['datasets']['physical-long']['comparison']['inference_bit_identical'])
        self.assertFalse(report['bounded_screen_pass'])
        self.assertEqual(len(commands), 3)

    def test_snapshot_gain_is_also_inference_drift(self):
        def change(kind, name, mode, row):
            if kind == 'snapshot' and mode == self.trial_mode:
                row['output']['matched'] += 1
                row['labels'][0]['matched'] += 1
                row['exact_matches_by_string_count']['3']['matched'] += 1
        report, commands = self.exercise(change=change)
        self.assertTrue(report['target_hold']['improved'])
        self.assertFalse(report['datasets']['physical-long']['comparison']['inference_bit_identical'])
        self.assertFalse(report['bounded_screen_pass'])
        self.assertEqual(len(commands), 3)


if __name__ == '__main__':
    unittest.main()
