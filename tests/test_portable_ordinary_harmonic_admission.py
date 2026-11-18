from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_calibrated_midi_retention_corpus as shared
from tools import portable_ordinary_harmonic_admission as trial
from tools import harmonic_competition_cues as competing


class HarmonicAdmissionRunnerTests(unittest.TestCase):
    def exercise(self, *, change=None, drift=None, failure=None, competition=False, energy_weighted_descriptor=False, common_detuning_support=False, local_onset_evidence=False, contradicted_retention=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus = root / 'corpus'
            corpus.mkdir()
            binary = root / 'replay'
            binary.write_text('fixture, never executed')
            inputs = {}
            for name in trial.INPUTS:
                path = corpus / name
                path.write_text(name)
                inputs[name] = dict(bytes=path.stat().st_size, sha256=trial.digest(path))
            source = dict(input_release='release', input_bundle_sha256='bundle',
                          original_input_manifest_sha256='manifest')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(dict(source=source, files=inputs)))
            labels = [dict(trial.PERSISTENCE_TARGET if contradicted_retention else (trial.LOCAL_ONSET_TARGET if local_onset_evidence else trial.TARGET), calibration_pass=0, labeled=10, matched=0),
                      dict(label_index=11, midi_note=47, string_mask=2,
                           start_sample=163306, end_sample=235200,
                           calibration_pass=0, labeled=10, matched=6)]
            base = dict(output=dict(labeled=20, matched=6, false_wrong_note_voices=1,
                false_wrong_string_voices=2, false_gap_voices=3, false_positive_voices=6,
                fingerprint='0123456789abcdef'), labels=labels,
                exact_matches_by_string_count={'1': dict(labeled=20, matched=6)})

            def mode_for(path):
                return next(mode for mode in (trial.OFF, trial.CURRENT, trial.TRIAL)
                            if mode in path.name)

            def parsed(path):
                mode = mode_for(path)
                row = deepcopy(base)
                if mode == trial.TRIAL:
                    row['output'].update(matched=8, fingerprint='fedcba9876543210')
                    row['labels'][0]['matched'] = 2
                    row['exact_matches_by_string_count']['1']['matched'] = 8
                    if change:
                        change('snapshot', row)
                return row

            def lifecycle(path, tsv, replay):
                mode = mode_for(path)
                rows = [dict({key: label[key] for key in shared.LABEL_IDENTITY},
                             exact_held_samples=0 if index == 0 else 5,
                             note_ons_inside_label=0 if index == 0 else 1)
                        for index, label in enumerate(labels)]
                if mode == trial.TRIAL:
                    rows[0].update(exact_held_samples=3, note_ons_inside_label=1)
                row = dict(coverage_valid=True, labels=rows, sample_count=trial.SAMPLES,
                    sample_rate=trial.RATE,
                    output_safety=dict(valid=True, counts=dict.fromkeys(shared.OUTPUT_SAFETY_FIELDS, 5)),
                    raw_midi=dict(counts=dict.fromkeys(shared.CONFLICT_FIELDS, 0)))
                if mode == trial.TRIAL and change:
                    change('held', row)
                row['exact_held_samples'] = sum(label['exact_held_samples'] for label in rows)
                return row

            references = dict(schema=trial.REFERENCE_SCHEMA, dataset='ordinary',
                settings=trial.SETTINGS, block_samples=512, source=source,
                reference_flags=trial.REFERENCE_FLAGS, inputs=inputs,
                config=competing.CONFIG if competition else trial.CONFIG,
                target=trial.TARGET, runs={},
                current_outcome_sha256=hashlib.sha256(b'shadow fixture').hexdigest())
            for mode in trial.REFERENCE_FLAGS:
                references['runs'][mode] = dict(output=base['output'],
                    exact_matches_by_string_count=base['exact_matches_by_string_count'],
                    tsv_sha256=hashlib.sha256(mode.encode()).hexdigest(), midi_trace_sha256=mode,
                    sample_count=trial.SAMPLES, sample_rate=trial.RATE)
            if drift == 'midi':
                references['runs'][trial.CURRENT]['midi_trace_sha256'] = 'changed'
            if drift == 'outcome':
                references['current_outcome_sha256'] = 'changed'
            if drift == 'config':
                references['config'] = dict(references['config'], minimum_independent_pairs=1)
            if drift == 'competition':
                references['config'] = trial.CONFIG
            reference_path = root / 'references.json'
            reference_path.write_text(json.dumps(references))
            if drift == 'input':
                (corpus / 'ordinary.tsv').write_text('different labels')
            commands, generated = [], []

            def native(command, stdout, stderr, **kwargs):
                mode = mode_for(Path(stdout.name))
                commands.append(command)
                self.assertEqual(command[command.index('--block') + 1], '512')
                self.assertEqual('--outcome-trace' in command, mode == trial.CURRENT)
                self.assertNotIn('--diagnostic-core-timing', command)
                self.assertEqual(trial.COLLISION in command, mode != trial.OFF)
                self.assertEqual('--candidate-rescue-harmonic-cues' in command, mode == trial.TRIAL and not (local_onset_evidence or contradicted_retention))
                self.assertEqual('--diagnostic-local-onset-evidence' in command,
                                 mode == trial.TRIAL and local_onset_evidence)
                if mode == trial.TRIAL and not (local_onset_evidence or contradicted_retention):
                    self.assertEqual(len(generated), 1)
                    cue = Path(command[command.index('--candidate-rescue-harmonic-cues') + 1])
                    self.assertTrue(cue.exists())
                    self.assertEqual(command[command.index('--candidate-rescue-score-ratio') + 1], '0.2')
                    self.assertEqual(command[command.index('--candidate-rescue-fundamental-ratio') + 1], '0.8')
                if failure == 'native':
                    stderr.write('named replay fixture failure')
                    raise subprocess.CalledProcessError(1, command)
                stdout.write(mode)
                Path(command[command.index('--midi-event-trace') + 1]).write_text('fixture')
                if mode == trial.CURRENT:
                    Path(command[command.index('--outcome-trace') + 1]).write_text('shadow fixture')

            def generate(audio, outcome, cues, evidence, deadline):
                generated.append(outcome)
                self.assertEqual(len(commands), 2)
                self.assertEqual(outcome.read_text(), 'shadow fixture')
                if failure == 'cue budget':
                    raise TimeoutError('fixture cue budget')
                cues.write_text('m3_harmonic_admission_cues_v1\t96000\t1024\n')
                evidence.write_bytes(b'fixture evidence')
                return dict(cue_spans=0, windows=10439, observations=0)

            def compress(path, **kwargs):
                return dict(raw_sha256=trial.digest(path) if 'outcome' in path.name else mode_for(path))

            output = root / 'output'
            with (patch.object(trial.subprocess, 'run', side_effect=native),
                  patch.object(trial, 'read_replay', side_effect=parsed),
                  patch.object(trial, 'analyze_midi', side_effect=lifecycle),
                  patch.object(trial, 'load_audio', return_value=object()),
                  patch.object(competing if competition else trial, 'generate', side_effect=generate),
                  patch.object(trial, 'compress_trace_window', side_effect=compress)):
                if drift or failure:
                    with self.assertRaises((ValueError, TimeoutError, subprocess.CalledProcessError)):
                        trial.run(binary, corpus, manifest, reference_path, output, competition=competition, energy_weighted_descriptor=energy_weighted_descriptor, common_detuning_support=common_detuning_support, local_onset_evidence=local_onset_evidence, contradicted_retention=contradicted_retention)
                else:
                    trial.run(binary, corpus, manifest, reference_path, output, competition=competition, energy_weighted_descriptor=energy_weighted_descriptor, common_detuning_support=common_detuning_support, local_onset_evidence=local_onset_evidence, contradicted_retention=contradicted_retention)
            report = json.loads((output / 'report.json').read_text())
            self.assertTrue(report['final'])
            self.assertFalse(report['promotion_accepted'])
            self.assertFalse(report['installed_output_changed'])
            for key in ('native_timing', 'allocations', 'buffer_identity', 'live_readiness'):
                self.assertEqual(report[key], 'not measured')
            return report, commands, generated

    def test_safe_gain_finishes_only_the_ordinary_offline_screen(self):
        report, commands, generated = self.exercise()
        self.assertEqual(len(commands), 3)
        self.assertEqual(len(generated), 1)
        self.assertTrue(report['bounded_screen_pass'])
        self.assertTrue(report['reference_identity_pass'])
        self.assertTrue(report['target_result']['improved'])
        self.assertFalse(report['comparison']['inference_identity_required'])

    def test_local_onset_is_isolated_and_preserves_rejection_gates(self):
        report, commands, generated = self.exercise(local_onset_evidence=True)
        self.assertTrue(report['bounded_screen_pass'])
        self.assertEqual(generated, [])
        self.assertEqual(report['target'], trial.LOCAL_ONSET_TARGET)
        self.assertEqual(report['conditions'][trial.TRIAL],
                         [trial.COLLISION, '--diagnostic-local-onset-evidence'])
        for kind in ('snapshot', 'held', 'false'):
            def lose(which, row):
                if kind == which:
                    row['labels'][1]['matched' if which == 'snapshot' else 'exact_held_samples'] = 0
                if kind == 'false' and which == 'snapshot':
                    row['output']['false_gap_voices'] += 1
                    row['output']['false_positive_voices'] += 1
            with self.subTest(kind=kind):
                report, _, _ = self.exercise(local_onset_evidence=True, change=lose)
                self.assertFalse(report['bounded_screen_pass'])

    def test_contradicted_retention_isolated_and_passage_loss_rejected(self):
        report, commands, generated = self.exercise(contradicted_retention=True)
        self.assertEqual(generated, [])
        self.assertEqual(report['target'], trial.PERSISTENCE_TARGET)
        self.assertEqual(report['conditions'][trial.TRIAL],
                         [trial.COLLISION, '--diagnostic-contradicted-retention'])
        self.assertEqual(['--diagnostic-contradicted-retention' in c for c in commands],
                         [False, False, True])
        def lose(kind, row):
            if kind == 'snapshot':
                row['labels'][1]['matched'] -= 1
        report, _, _ = self.exercise(contradicted_retention=True, change=lose)
        self.assertFalse(report['bounded_screen_pass'])
        with self.assertRaisesRegex(ValueError, 'must be isolated'):
            trial.run(None, None, None, None, None,
                      contradicted_retention=True, persistent_candidate_admission=True)

    def test_common_detuning_support_applies_only_to_trial(self):
        report, commands, _ = self.exercise(common_detuning_support=True)
        self.assertTrue(report['common_detuning_support'])
        flag = '--diagnostic-common-detuning-support'
        self.assertEqual([flag in command for command in commands], [False, False, True])
        self.assertFalse(report['energy_weighted_descriptor'])

    def test_energy_weighting_applies_only_to_trial(self):
        report, commands, _ = self.exercise(energy_weighted_descriptor=True)
        self.assertTrue(report['energy_weighted_descriptor'])
        flag = '--diagnostic-energy-weighted-descriptor'
        self.assertEqual([flag in command for command in commands], [False, False, True])

    def test_competition_selects_its_generator_and_frozen_policy(self):
        report, commands, generated = self.exercise(competition=True)
        self.assertEqual(len(commands), 3)
        self.assertEqual(len(generated), 1)
        self.assertEqual(report['config'], competing.CONFIG)
        self.assertTrue(report['bounded_screen_pass'])
        report, commands, generated = self.exercise(competition=True, drift='competition')
        self.assertEqual(commands, [])
        self.assertEqual(generated, [])
        self.assertFalse(report['bounded_screen_pass'])

    def test_target_without_new_hold_or_snapshot_gain_is_rejected(self):
        for missing in ('held', 'snapshot'):
            def change(kind, row):
                if kind == missing:
                    row['labels'][0]['exact_held_samples' if kind == 'held' else 'matched'] = 0
            with self.subTest(missing=missing):
                report, _, _ = self.exercise(change=change)
                self.assertFalse(report['bounded_screen_pass'])
                self.assertEqual(report['state'], 'rejected')

    def test_one_other_passage_loss_rejects_even_with_target_gain(self):
        for lost in ('held', 'snapshot'):
            def change(kind, row):
                if kind == lost:
                    row['labels'][1]['exact_held_samples' if kind == 'held' else 'matched'] -= 1
            with self.subTest(lost=lost):
                report, _, _ = self.exercise(change=change)
                self.assertTrue(report['target_result']['improved'])
                self.assertFalse(report['note_safety_pass'])
                self.assertFalse(report['bounded_screen_pass'])

    def test_every_false_output_and_pairing_conflict_growth_rejects(self):
        for group, fields in (('output_safety', shared.OUTPUT_SAFETY_FIELDS),
                              ('raw_midi', shared.CONFLICT_FIELDS)):
            for field in fields:
                def change(kind, row):
                    if kind == 'held':
                        row[group]['counts'][field] += 1
                with self.subTest(group=group, field=field):
                    report, _, _ = self.exercise(change=change)
                    self.assertFalse(report['bounded_screen_pass'])

    def test_each_snapshot_false_output_growth_rejects(self):
        for field in ('false_wrong_note_voices', 'false_wrong_string_voices',
                      'false_gap_voices', 'false_positive_voices'):
            def change(kind, row):
                if kind == 'snapshot':
                    row['output'][field] += 1
            with self.subTest(field=field):
                report, _, _ = self.exercise(change=change)
                self.assertFalse(report['bounded_screen_pass'])

    def test_invalid_pairing_or_changed_clock_rejects(self):
        for field in ('coverage_valid', 'sample_count', 'sample_rate'):
            def change(kind, row):
                if kind == 'held':
                    row[field] = False if field == 'coverage_valid' else row[field] + 1
            with self.subTest(field=field):
                report, _, _ = self.exercise(change=change)
                self.assertFalse(report['bounded_screen_pass'])

    def test_reference_and_outcome_drift_prevent_cue_generation_and_trial(self):
        for drift in ('midi', 'outcome'):
            with self.subTest(drift=drift):
                report, commands, generated = self.exercise(drift=drift)
                self.assertEqual(len(commands), 2)
                self.assertEqual(generated, [])
                self.assertFalse(report['reference_identity_pass'])
                self.assertFalse(report['bounded_screen_pass'])

    def test_input_or_policy_drift_prevents_any_replay(self):
        for drift in ('input', 'config'):
            with self.subTest(drift=drift):
                report, commands, generated = self.exercise(drift=drift)
                self.assertEqual(commands, [])
                self.assertEqual(generated, [])
                self.assertFalse(report['bounded_screen_pass'])

    def test_budget_failure_does_not_run_trial_or_claim_complete_cues(self):
        report, commands, _ = self.exercise(failure='cue budget')
        self.assertEqual(len(commands), 2)
        self.assertEqual(report['state'], 'failed')
        self.assertNotIn('cue_generation', report)
        self.assertFalse(report['bounded_screen_pass'])

    def test_native_failure_retains_named_stderr(self):
        report, commands, _ = self.exercise(failure='native')
        self.assertEqual(len(commands), 1)
        self.assertEqual(report['state'], 'failed')
        self.assertEqual(report['failure_stderr_tail'], 'named replay fixture failure')

    def test_saved_selection_is_consistent_with_existing_full_file_anchors(self):
        root = Path(__file__).resolve().parents[1] / 'docs/recovery'
        selected = json.loads((root / 'ordinary-harmonic-tuning-references-20261116.json').read_text())
        corpus = json.loads((root / 'calibrated-midi-retention-corpus-references-20261115.json').read_text())
        partial = json.loads((root / 'ordinary-partial-references-20261116.json').read_text())
        self.assertEqual(selected['runs'], corpus['datasets']['ordinary'])
        self.assertEqual(selected['current_outcome_sha256'], partial['replay_reference']['outcome_sha256'])
        self.assertEqual(selected['inputs'], partial['inputs'])
        self.assertEqual(selected['config'], trial.CONFIG)
        competition = json.loads((root / 'ordinary-harmonic-competition-references-20261116.json').read_text())
        fixed = json.loads((root / 'ordinary-harmonic-fixed-competition-references-20261116.json').read_text())
        for key in ('runs', 'inputs', 'current_outcome_sha256', 'source', 'target'):
            self.assertEqual(competition[key], selected[key])
        for key in competition.keys() - {'config', 'policy_revision'}:
            self.assertEqual(fixed[key], competition[key])
        self.assertEqual(fixed['config'], competing.CONFIG)


if __name__ == '__main__':
    unittest.main()
