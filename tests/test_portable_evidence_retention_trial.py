import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.frozen_cue_corpus_gate import COUNTS, ERRORS, LABEL_FIELDS, read_replay
from tools.portable_assignment_trace import digest
from tools.portable_evidence_retention_trial import run, summarize_target, summarize_calibrated_output


def replay_text(*, target=0, other=1, false_notes=0, transitions=2, target_start=0):
    labels = [dict(label_index=i, start_sample=0, end_sample=192, midi_note=60,
                   string_mask=1, calibration_pass=0, labeled=3, matched=0)
              for i in range(56)]
    labels[0]['matched'] = other
    labels[55].update(midi_note=42, matched=target, start_sample=target_start,
                      labeled=(192 - target_start) // 64)
    output = {key: 0 for key in COUNTS}
    output.update(labeled=sum(label['labeled'] for label in labels), matched=other + target,
                  false_wrong_note_voices=false_notes, false_positive_voices=false_notes,
                  fingerprint='0123456789abcdef', samples=192, sample_rate=96000,
                  transitions=transitions)
    text = io.StringIO()
    aggregate = csv.DictWriter(text, fieldnames=output, delimiter='\t')
    aggregate.writeheader()
    aggregate.writerow(output)
    details = csv.DictWriter(text, fieldnames=LABEL_FIELDS, delimiter='\t')
    details.writeheader()
    details.writerows(labels)
    return text.getvalue()


def outcome_rows():
    result = []
    for tick in range(1, 4):
        fields = ['0'] * 42
        fields[0], fields[1], fields[10] = '42', '4', '1'
        fields[2] = '1' if tick == 2 else '0'
        fields[26] = '51' if tick == 1 else '0'
        result.append(dict(sample=str(tick * 64 - 1), tick=str(tick),
                           quiet='0', signal_samples='0', labels='55:42:1',
                           matched_labels='', voices='',
                           candidates=':'.join(fields)))
    return result


def calibrated_rows():
    rows = []
    for tick, reason in enumerate(('projection_apply', 'ineligible', 'untrusted_revert'), 1):
        fields = dict(tick=tick, eligibility_failures=0, age=200, min_age=75,
                      selected_count=2, member_mask=1, output_before=41, output_after=42,
                      midi_before=41, midi_after=42, target_before=42, target_after=42,
                      ticks_before=1, ticks_after=2, projected_note=42, changed=1, trusted=1,
                      collision_note=255, collision_kind=0, transitions_added=2,
                      observed=1, reason=reason, phase_cents='60', projected_error_cents='0')
        if tick == 2:
            fields.update(eligibility_failures=1, output_before=42, midi_before=42,
                          target_after=255, ticks_after=0, transitions_added=0)
        elif tick == 3:
            fields.update(output_before=42, midi_before=42, output_after=41, midi_after=41,
                          trusted=0, changed=0, target_before=41, target_after=255, ticks_after=0)
        rows.append(dict(sample=str(tick * 64 - 1), tick=str(tick), note='41',
                         **{'cal_' + key: str(value) for key, value in fields.items()}))
    return rows


class PortableEvidenceRetentionTrialTests(unittest.TestCase):
    def fixture(self, root, *, baseline_text=None):
        corpus = root / 'corpus'
        corpus.mkdir()
        for name in ('ordinary.wav', 'ordinary.tsv', 'calibration.m3cb', 'templates.tsv'):
            (corpus / name).write_text(name)
        manifest = root / 'manifest.json'
        manifest.write_text(json.dumps({'files': {
            path.name: {'sha256': digest(path)} for path in corpus.iterdir()}}))
        binary = root / 'replay'
        binary.write_text('fake binary; subprocess is mocked')
        baseline = root / 'baseline.tsv'
        baseline.write_text(replay_text() if baseline_text is None else baseline_text)
        reference = root / 'reference.json'
        reference.write_text(json.dumps({'runs': {'reference-off': {
            'tsv_sha256': digest(baseline), 'output': read_replay(baseline)['output']}}}))
        return binary, corpus, manifest, reference, root / 'output'

    def replay_stub(self, after, *, calibrated=False, projection=False, before=None,
                    full_midi=False, invalid_pair=False):
        def replay(command, *, stdout, stderr, check, timeout):
            self.assertTrue(check)
            self.assertGreater(timeout, 0)
            self.assertNotIn('--diagnostic-native-partial-cues', command)
            self.assertNotIn('--diagnostic-cue-free-lane-reassignment', command)
            enabled = '--diagnostic-direct-evidence-retention' in command
            traced = '--candidate-trace' in command
            self.assertEqual('--diagnostic-projection-preview-admission' in command,
                             projection and traced)
            if calibrated or projection:
                self.assertFalse(enabled)
                if traced:
                    self.assertEqual(command[command.index('--candidate-trace-note') + 1], '41')
            stdout.write(after if traced else (replay_text() if before is None else before))
            if traced:
                for kind in ('candidate', 'outcome'):
                    path = Path(command[command.index('--' + kind + '-trace') + 1])
                    if kind == 'outcome':
                        rows = outcome_rows()
                    elif kind == 'candidate':
                        rows = (calibrated_rows() if calibrated or projection else
                                [dict(sample=row['sample'], note='42') for row in outcome_rows()])
                    with path.open('w') as stream:
                        writer = csv.DictWriter(stream, fieldnames=rows[0], delimiter='\t')
                        writer.writeheader()
                        writer.writerows(rows)
            if '--midi-event-trace' in command:
                self.assertEqual(command.count('--midi-event-trace'), 1)
                path = Path(command[command.index('--midi-event-trace') + 1])
                note = 42 if traced else 41
                onset = 63 if full_midi else 127
                rows = [dict(sample=onset if traced else 0, kind='on', note=note,
                             velocity=100, voice_id=0, sequence=1),
                        dict(sample=191, kind='off', note=43 if traced and invalid_pair else note,
                             velocity=0, voice_id=0, sequence=2)]
                with path.open('w') as stream:
                    stream.write('# m3_midi_events_v1\n')
                    writer = csv.DictWriter(stream, fieldnames=rows[0], delimiter='\t')
                    writer.writeheader()
                    writer.writerows(rows)
        return replay

    def test_target_requires_complete_trace_and_does_not_infer_midi_from_state(self):
        label = dict(label_index=55, start_sample=0, end_sample=192, midi_note=42,
                     string_mask=1)
        rows = outcome_rows()
        result = summarize_target(rows, [], label)
        self.assertEqual(result['counts']['active'], 1)
        self.assertEqual(result['midi_events_during_label'], [])
        for invalid in (rows[:-1], rows + [rows[0]]):
            with self.subTest(rows=len(invalid)), self.assertRaises(ValueError):
                summarize_target(invalid, [], label)

    def test_preview_matches_and_retuned_neighbor_are_not_target_midi_activity(self):
        label = dict(label_index=55, start_sample=0, end_sample=192, midi_note=42,
                     string_mask=1)
        rows = outcome_rows()
        for row in rows:
            fields = row['candidates'].split(':')
            fields[2] = '0'
            row['candidates'] = ':'.join(fields)
            row['matched_labels'] = '55'
        # Pitch-bend validity must not turn an inactive preview into an active source.
        rows[0]['voices'] = '42:42:0:0:0:1:0:1'
        neighbor = rows[1]['candidates'].split(':')
        neighbor[0], neighbor[2] = '41', '1'
        rows[1]['candidates'] += ',' + ':'.join(neighbor)
        # An active source may have no valid pitch bend and a different logical note.
        rows[1]['voices'] = '41:42:0:0:10:0:0:1'
        rows[2]['voices'] = '41:41:2:1:11:1:0:4,42:42:0:0:0:0:0:1'
        events = [dict(sample='127', kind='on', note='42', voice_id='0'),
                  dict(sample='191', kind='off', note='42', voice_id='0')]
        result = summarize_target(rows, events, label)
        self.assertEqual(result['counts']['active'], 0)
        self.assertEqual(result['snapshot_counts'], dict(matched=3,
            matched_with_active_source=1, matched_inactive_preview_only=2,
            matched_source_unknown=0, rendered_note_with_active_source_any_string=1))
        self.assertEqual(result['midi_events_during_label'][0][
            'matching_snapshot_active_source_notes'], [41])
        self.assertEqual(result['midi_events_during_label'][0]['snapshot_source_status'], 'unique')
        self.assertNotIn('matching_snapshot_active_source_notes', result['midi_events_during_label'][1])
        missing = summarize_target(rows, None, label)
        self.assertEqual(missing['midi_event_capture'], 'not measured')

    def test_unknown_or_multiple_sources_do_not_get_unique_midi_attribution(self):
        label = dict(label_index=55, start_sample=0, end_sample=192, midi_note=42,
                     string_mask=1)
        rows = outcome_rows()
        rows[0].update(matched_labels='55', voices='41:42:0:0:10:1:0:1')
        neighbor = rows[1]['candidates'].split(':')
        neighbor[0] = '41'
        rows[1]['candidates'] += ',' + ':'.join(neighbor)
        rows[1]['voices'] = '41:42:0:0:10:1:0:1,42:42:0:0:10:1:0:1'
        events = [dict(sample=str(sample), kind='on', note='42', voice_id='0')
                  for sample in (63, 127)]
        result = summarize_target(rows, events, label)
        self.assertEqual(result['snapshot_counts']['matched_source_unknown'], 1)
        self.assertEqual([row['snapshot_source_status'] for row in result['midi_events_during_label']],
                         ['unknown', 'ambiguous'])

    def test_changed_off_reference_stops_before_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(Path(directory))
            reference = json.loads(args[3].read_text())
            reference['runs']['reference-off']['tsv_sha256'] = '0' * 64
            args[3].write_text(json.dumps(reference))
            with patch('tools.portable_evidence_retention_trial.subprocess.run',
                       side_effect=self.replay_stub(replay_text(target=2))) as replay:
                with self.assertRaisesRegex(ValueError, 'OFF reference differs'):
                    run(*args)
            self.assertEqual(replay.call_count, 1)
            result = json.loads((args[4] / 'report.json').read_text())
            self.assertEqual(result['state'], 'failed')
            self.assertTrue(result['final'])
            self.assertFalse(result['promotion_accepted'])

    def test_gain_does_not_hide_lost_label_or_extra_false_notes(self):
        for change in (dict(target=2, other=0), dict(target=2, false_notes=1)):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                args = self.fixture(Path(directory))
                with patch('tools.portable_evidence_retention_trial.subprocess.run',
                           side_effect=self.replay_stub(replay_text(**change))):
                    run(*args)
                result = json.loads((args[4] / 'report.json').read_text())
                self.assertTrue(result['labeled_match_gain'])
                self.assertFalse(result['full_recording_screen_pass'])
                self.assertEqual(result['decision'], 'rejected')
                self.assertFalse(result['installed_output_changed'])

    def test_clean_gain_is_only_eligible_for_wider_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(Path(directory))
            with patch('tools.portable_evidence_retention_trial.subprocess.run',
                       side_effect=self.replay_stub(replay_text(target=2))):
                run(*args)
            result = json.loads((args[4] / 'report.json').read_text())
            self.assertEqual(result['decision'], 'eligible for wider validation')
            self.assertFalse(result['promotion_accepted'])
            self.assertEqual(result['native_timing'], 'not measured')
            self.assertEqual(len(result['target_lifecycle']['midi_events_during_label']), 2)
            self.assertEqual(result['comparison']['lost_labels'], [])
            self.assertEqual(result['comparison']['increased_error_counts'], [])
            self.assertTrue(all(result['comparison']['delta'][key] == 0 for key in ERRORS))
            for trace in result['traces'].values():
                self.assertEqual(digest(args[4] / trace['file']), trace['sha256'])
            self.assertFalse((args[4] / 'outcome.tsv').exists())
            self.assertNotIn('midi_lifecycle_comparison', result)
            self.assertNotIn('midi_lifecycle', result['runs']['reference-off'])
            self.assertFalse((args[4] / 'reference-off-midi.tsv.gz').exists())

    def test_optional_lifetimes_use_and_retain_events_before_the_diagnostic_window(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = replay_text(target_start=128)
            args = self.fixture(Path(directory), baseline_text=baseline)
            with patch('tools.portable_evidence_retention_trial.subprocess.run',
                       side_effect=self.replay_stub(replay_text(target=1, target_start=128),
                           projection=True, before=baseline, full_midi=True)) as replay:
                run(*args, projection_preview_trial=True, capture_midi_lifecycle=True)
            result = json.loads((args[4] / 'report.json').read_text())
            self.assertEqual(replay.call_count, 2)
            self.assertTrue(result['off_reference_bit_identical'])
            self.assertFalse(result['promotion_accepted'])
            off = result['runs']['reference-off']['midi_lifecycle']
            on = result['runs']['trial-on']['midi_lifecycle']
            self.assertTrue(off['coverage_valid'] and on['coverage_valid'])
            self.assertEqual(off['labels'][55]['exact_held_samples'], 0)
            self.assertEqual(on['labels'][55]['exact_held_samples'], 63)
            self.assertEqual(on['labels'][55]['note_ons_inside_label'], 0)
            self.assertEqual(result['midi_lifecycle_comparison']['exact_held_samples_delta'], 63)
            self.assertEqual(result['midi_lifecycle_comparison']['changed_labels'], [
                dict(label_index=55, delta=dict(exact_held_samples=63,
                     longest_exact_hold_samples=63, note_ons_inside_label=0))])
            for name, first_sample in (('reference-off-midi', 0), ('midi-event', 63)):
                trace = result['traces'][name]
                self.assertEqual(trace['discarded_rows'], 0)
                self.assertEqual(trace['retained_rows'], 2)
                self.assertEqual(trace['raw_sha256'], trace['captured_raw_sha256'])
                self.assertEqual(digest(args[4] / trace['file']), trace['sha256'])
                with gzip.open(args[4] / trace['file'], 'rt') as stream:
                    self.assertEqual(stream.readline().strip(), '# m3_midi_events_v1')
                    rows = list(csv.DictReader(stream, delimiter='\t'))
                self.assertEqual(int(rows[0]['sample']), first_sample)
            self.assertEqual(result['traces']['outcome']['start_sample_inclusive'], 64)

    def test_incomplete_midi_stream_fails_before_trace_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(Path(directory))
            with patch('tools.portable_evidence_retention_trial.subprocess.run',
                       side_effect=self.replay_stub(replay_text(target=2, transitions=3),
                                                   projection=True)):
                with self.assertRaisesRegex(ValueError, 'differs from replay transition count'):
                    run(*args, projection_preview_trial=True, capture_midi_lifecycle=True)
            result = json.loads((args[4] / 'report.json').read_text())
            self.assertEqual(result['state'], 'failed')
            self.assertFalse(result['promotion_accepted'])
            self.assertTrue((args[4] / 'midi-event.tsv').exists())
            self.assertFalse((args[4] / 'midi-event.tsv.gz').exists())

    def test_pairing_anomalies_do_not_produce_a_held_note_improvement(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(Path(directory))
            with patch('tools.portable_evidence_retention_trial.subprocess.run',
                       side_effect=self.replay_stub(replay_text(target=2), projection=True,
                                                   invalid_pair=True)):
                run(*args, projection_preview_trial=True, capture_midi_lifecycle=True)
            result = json.loads((args[4] / 'report.json').read_text())
            self.assertFalse(result['midi_lifecycle_comparison']['coverage_valid'])
            self.assertIsNone(result['midi_lifecycle_comparison']['exact_held_samples_delta'])
            self.assertIsNone(result['midi_lifecycle_comparison']['changed_labels'])
            self.assertEqual(result['runs']['trial-on']['midi_lifecycle']['event_error_counts'],
                             dict(note_off_without_matching_note_on=1))
            self.assertFalse(result['promotion_accepted'])

    def test_baseline_trace_requires_identity_and_retains_actual_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(Path(directory))
            with patch('tools.portable_evidence_retention_trial.subprocess.run',
                       side_effect=self.replay_stub(replay_text(), calibrated=True)) as replay:
                run(*args, calibrated_output_trace=True)
            result = json.loads((args[4] / 'report.json').read_text())
            self.assertEqual(replay.call_count, 2)
            self.assertTrue(result['trace_output_bit_identical'])
            self.assertTrue(result['trace_semantic_identity'])
            self.assertFalse(result['runtime_rule_changed'])
            self.assertFalse(result['promotion_accepted'])
            self.assertEqual(result['decision'], 'unchanged baseline; diagnostic collected')
            self.assertEqual(result['calibrated_output']['output_change_reasons'],
                             dict(projection_apply=1, untrusted_revert=1))
            # The ineligible stage did not emit the separately captured note-on.
            coast = result['calibrated_output']['transitions'][1]
            self.assertEqual(coast['stage']['reason'], 'ineligible')
            self.assertEqual(coast['stage']['transitions_added'], 0)
            self.assertEqual(coast['midi_events_at_same_tick'][0]['kind'], 'on')

    def test_semantically_equal_trace_with_changed_bytes_stops_before_diagnosis(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(Path(directory))
            with patch('tools.portable_evidence_retention_trial.subprocess.run',
                       side_effect=self.replay_stub(replay_text() + '\n', calibrated=True)):
                with self.assertRaisesRegex(ValueError, 'Traced OFF replay differs'):
                    run(*args, calibrated_output_trace=True)
            result = json.loads((args[4] / 'report.json').read_text())
            self.assertFalse(result['trace_output_bit_identical'])
            self.assertTrue(result['trace_semantic_identity'])
            self.assertNotIn('calibrated_output', result)
            self.assertEqual(result['state'], 'failed')

    def test_projection_trial_traces_owner_and_keeps_full_recording_gates(self):
        for change, decision in ((dict(target=2), 'eligible for wider validation'),
                                 (dict(target=2, other=0), 'rejected'),
                                 (dict(target=2, false_notes=1), 'rejected')):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                args = self.fixture(Path(directory))
                with patch('tools.portable_evidence_retention_trial.subprocess.run',
                           side_effect=self.replay_stub(replay_text(**change), projection=True)):
                    run(*args, projection_preview_trial=True)
                result = json.loads((args[4] / 'report.json').read_text())
                self.assertTrue(result['off_reference_bit_identical'])
                self.assertTrue(result['runtime_rule_changed'])
                self.assertEqual(result['calibrated_output']['candidate_note'], 41)
                self.assertEqual(result['decision'], decision)
                self.assertFalse(result['promotion_accepted'])
                self.assertFalse(result['installed_output_changed'])
                self.assertNotIn('trace_output_bit_identical', result)

    def test_trace_and_trial_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(Path(directory))
            with self.assertRaisesRegex(ValueError, 'either unchanged tracing'):
                run(*args, calibrated_output_trace=True, projection_preview_trial=True)
            self.assertFalse(args[4].exists())

    def test_stage_capture_rejects_stale_tick_and_missing_candidate_rows(self):
        rows = calibrated_rows()
        rows[0]['cal_tick'] = '0'
        with self.assertRaisesRegex(ValueError, 'Stale'):
            summarize_calibrated_output(rows, outcome_rows(), [], 41)
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            summarize_calibrated_output(calibrated_rows()[:-1], outcome_rows(), [], 41)


if __name__ == '__main__':
    unittest.main()
