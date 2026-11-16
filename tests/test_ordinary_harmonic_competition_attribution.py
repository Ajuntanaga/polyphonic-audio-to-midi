import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import ordinary_harmonic_competition_attribution as subject
from tests.test_ordinary_harmonic_attribution import events, spec


def decisions():
    before = [dict(available_sample=1023, baseline_state_sample=63,
        window_start_sample=-3776, candidate_note=note, base_pitches=[],
        admitted=True, status='prediction_pass') for note in (72, 74, 75)]
    before.append(dict(available_sample=2047, baseline_state_sample=None,
        window_start_sample=-2752, candidate_note=71, admitted=False,
        status='insufficient_history'))
    after = [dict(row, original_status=row['status'], lower_comparisons=[],
        status='competition_pass' if row['admitted'] else row['status']) for row in before]
    after[0].update(admitted=False, status='lower_competition_withheld', withholding_lower_note=60)
    after[1]['lower_comparisons'] = [dict(lower=dict(note=62),
        independent_lower_support=dict(admitted=False, status='insufficient_supported_pairs'))]
    return before, after


def make_archives(root):
    labels = [dict(label_index=i, midi_note=note, string_mask=mask,
        start_sample=1024, end_sample=3072) for i, (note, mask) in enumerate(((75, 1), (60, 2)))]
    current = events([(1024, 3072, 60, 1)])
    common = [(1024, 3072, 75, 0), (1024, 2048, 60, 1), (2048, 3072, 60, 2),
              (1024, 1536, 74, 3), (3072, None, 74, 3)]
    reference = dict(schema='m3_ordinary_harmonic_competition_attribution_references_v1',
        focus_labels=[0, 1], focus_cue=dict(available_sample=1023, candidate_note=74), screens={})
    archives = {}
    for index, (name, rows) in enumerate(zip(subject.SCREENS, decisions())):
        small, bulk = root / (name + '-small.zip'), root / (name + '-bulk.zip')
        trial = events(common + ([(1536, 2560, 72, 4)] if name == 'tuning' else []))
        manifest = json.dumps(dict(files={'ordinary.wav': dict(bytes=8192, sha256='shared-audio')},
            source=dict(commit=str(index) * 40, run_id=str(index + 1), input_release='shared',
                        input_bundle_sha256='shared-bundle', original_input_manifest_sha256='shared-manifest'))).encode()
        saved = dict(final=True, source=dict(commit=str(index) * 40, run_id=index + 1),
                     input_manifest_sha256=spec(manifest)['sha256'], runs={})
        with zipfile.ZipFile(bulk, 'w') as archive:
            for mode, trace, holds, totals in (
                (subject.CURRENT, current, [0, 2048], [2048, 0, 0, 0]),
                (subject.TRIAL, trial, [2048, 1024], [3072, 1536 if name == 'tuning' else 512, 1024, 1024])):
                fields = ('sample', 'kind', 'note', 'velocity', 'voice_id', 'sequence')
                raw = ('# m3_midi_events_v1\n' + '\t'.join(fields) + '\n' +
                    ''.join('\t'.join(str(row[field]) for field in fields) + '\n' for row in trace)).encode()
                packed = gzip.compress(raw)
                filename = mode + '.tsv.gz'
                archive.writestr(filename, packed)
                saved['runs'][mode] = dict(sample_count=4096, sample_rate=96000,
                    outcome_sha256='shared-outcome',
                    midi_trace=dict(file=filename, **spec(packed), raw_bytes=len(raw), raw_sha256=spec(raw)['sha256']),
                    midi_lifecycle=dict(transitions=len(trace), labels=[dict(row, exact_held_samples=hold)
                        for row, hold in zip(labels, holds)], output_safety=dict(counts={
                        kind + '_voice_samples': n for kind, n in zip(subject.attribution.KINDS, totals)})))
            admitted = [row for row in rows if row['admitted']]
            cues = (subject.attribution.CUE_HEADER + ''.join(
                f"1024\t2048\t{row['candidate_note']}\n" for row in admitted)).encode()
            evidence = gzip.compress(('\n'.join(json.dumps(row) for row in rows) + '\n').encode())
            archive.writestr('ordinary-harmonic-admission-cues.tsv', cues)
            archive.writestr('ordinary-harmonic-admission-evidence.jsonl.gz', evidence)
            saved['cue_generation'] = dict(cue_spans=len(admitted), cue_bytes=len(cues),
                cue_sha256=spec(cues)['sha256'], evidence_bytes=len(evidence), evidence_sha256=spec(evidence)['sha256'],
                statuses={'lower_competition_withheld': 1} if name == 'competition' else {})
        report = json.dumps(saved).encode()
        with zipfile.ZipFile(small, 'w') as archive:
            archive.writestr(name + '/report.json', report)
            archive.writestr('runtime-manifest.json', manifest)
        reference['screens'][name] = dict(schema='m3_ordinary_harmonic_attribution_references_v1',
            source_commit=str(index) * 40, run_id=index + 1, report=dict(file=name + '/report.json', **spec(report)),
            small_artifact=spec(small.read_bytes()), bulk_artifact=spec(bulk.read_bytes()))
        archives[name] = small, bulk
    path = root / 'reference.json'
    path.write_text(json.dumps(reference))
    return path, archives


class PairedAttributionTests(unittest.TestCase):
    def test_retained_pair_identifies_withdrawal_and_preserved_gain_and_loss(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference, archives = make_archives(root)
            report = subject.analyze(reference, archives, root / 'output')
            self.assertTrue(report['shared_current_identity_pass'])
            self.assertEqual(report['withheld_count'], 1)
            self.assertEqual(report['withheld_by_upper_lower'], [dict(upper=72, lower=60, count=1)])
            self.assertEqual(report['withheld_annotation_pitch_samples'], dict(other_labeled_pitch=1024))
            self.assertEqual(report['competition_vs_tuning']['change_totals']['false_wrong_note'],
                             dict(added=0, removed=1024))
            for name in subject.SCREENS:
                cases = report['per_screen_vs_current'][name]['cases']
                self.assertEqual([row['net_exact_change'] for row in cases], [2048, -1024])
                self.assertEqual(cases[1]['loss_causes'], dict(wrong_or_incomplete_assignment=1024))
            self.assertEqual(report['known_false_note']['competition_decision']['status'], 'competition_pass')
            self.assertEqual(report['target']['admitted_cues'], 1)
            rows = json.loads((root / 'output/withheld-cues.json').read_text())
            self.assertEqual(rows[0]['overlapping_same_pitch_output_changes'][0]['overlap_voice_samples'], 512)
            self.assertFalse(report['audio_processed'])
            self.assertEqual(report['native_replays'], 0)

    def test_noncausal_or_changed_observation_stops_comparison(self):
        for field, value in [('baseline_state_sample', 64), ('window_start_sample', 123), ('candidate_note', 80)]:
            with self.subTest(field=field):
                before, after = decisions()
                after[0][field] = value
                with self.assertRaises(ValueError):
                    subject.match_observations(before, after)

    def test_new_admission_stops_comparison(self):
        before, after = decisions()
        after[-1]['admitted'] = True
        with self.assertRaisesRegex(ValueError, 'added an admission'):
            subject.match_observations(before, after)

    def test_fitted_parent_difference_is_reported_not_treated_as_changed_input(self):
        before, after = decisions()
        for row in (before[0], after[0]):
            row.update(parent_tuning=dict(status='fitted'), base_pitches=[
                dict(note=40, frequency_hz=82., phase_cents=0., phase_valid=False)])
        after[0]['base_pitches'][0]['frequency_hz'] = 82.000000000001
        _, _, _, differences = subject.match_observations(before, after)
        self.assertEqual(len(differences), 1)
        self.assertGreater(differences[0]['parents'][0]['difference_cents'], 0.)
        for field, value in [('note', 41), ('phase_cents', 1.), ('phase_valid', True)]:
            changed = copy.deepcopy(after)
            changed[0]['base_pitches'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Causal parent'):
                subject.match_observations(before, changed)
        after[0]['original_status'] = 'prediction_rejected'
        with self.assertRaisesRegex(ValueError, 'Original decision'):
            subject.match_observations(before, after)

    def test_saved_phase_frequency_must_remain_identical(self):
        old = dict(base_pitches=[dict(note=40, frequency_hz=82., phase_valid=True)])
        new = copy.deepcopy(old)
        new['base_pitches'][0]['frequency_hz'] = 83.
        with self.assertRaisesRegex(ValueError, 'Causal parent'):
            subject.compare_parent_inputs(old, new)

    def test_different_reference_stops_pairing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, archives = make_archives(Path(temporary))
            refs = json.loads(path.read_text())['screens']
            screens = {name: subject.load_screen(refs[name], *archives[name]) for name in subject.SCREENS}
            changed = copy.deepcopy(screens)
            changed['competition']['events'][subject.CURRENT][0]['note'] = 61
            with self.assertRaisesRegex(ValueError, 'current MIDI differs'):
                subject.require_shared_reference(changed)

    def test_run_metadata_can_differ_but_input_bytes_and_provenance_cannot(self):
        before = dict(files={'ordinary.wav': dict(bytes=8, sha256='audio')}, source=dict(
            commit='a', run_id=1, input_release='release', input_bundle_sha256='bundle',
            original_input_manifest_sha256='manifest'))
        after = copy.deepcopy(before)
        after['source'].update(commit='b', run_id=2)
        subject.require_shared_inputs(before, after)
        after['files']['ordinary.wav']['sha256'] = 'different-audio'
        with self.assertRaisesRegex(ValueError, 'input file identities'):
            subject.require_shared_inputs(before, after)
        after = copy.deepcopy(before)
        after['source']['input_bundle_sha256'] = 'different-bundle'
        with self.assertRaisesRegex(ValueError, 'input provenance'):
            subject.require_shared_inputs(before, after)

    def test_runtime_manifest_is_bound_to_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, archives = make_archives(Path(temporary))
            refs = json.loads(path.read_text())['screens']
            with zipfile.ZipFile(archives['tuning'][0]) as archive:
                saved = json.loads(archive.read(refs['tuning']['report']['file']))
            saved['input_manifest_sha256'] = 'different'
            with self.assertRaisesRegex(ValueError, 'manifest hash differs'):
                subject.read_input_manifest(archives['tuning'][0], saved)

    def test_pitch_classification_does_not_double_count_overlapping_labels(self):
        labels = [dict(start_sample=0, end_sample=10, midi_note=75),
                  dict(start_sample=5, end_sample=15, midi_note=75),
                  dict(start_sample=10, end_sample=20, midi_note=60)]
        self.assertEqual(subject.expected_pitch_intervals(labels, 0, 24, 75),
                         dict(expected_pitch=15, other_labeled_pitch=5, unlabeled_gap=4))


if __name__ == '__main__':
    unittest.main()
