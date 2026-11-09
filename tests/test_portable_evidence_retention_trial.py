import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.frozen_cue_corpus_gate import COUNTS, ERRORS, LABEL_FIELDS, read_replay
from tools.portable_assignment_trace import digest
from tools.portable_evidence_retention_trial import run, summarize_target


def replay_text(*, target=0, other=1, false_notes=0):
    labels = [dict(label_index=i, start_sample=0, end_sample=192, midi_note=60,
                   string_mask=1, calibration_pass=0, labeled=3, matched=0)
              for i in range(56)]
    labels[0]['matched'] = other
    labels[55].update(midi_note=42, matched=target)
    output = {key: 0 for key in COUNTS}
    output.update(labeled=168, matched=other + target,
                  false_wrong_note_voices=false_notes, false_positive_voices=false_notes,
                  fingerprint='0123456789abcdef', samples=192, sample_rate=96000)
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


class PortableEvidenceRetentionTrialTests(unittest.TestCase):
    def fixture(self, root):
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
        baseline.write_text(replay_text())
        reference = root / 'reference.json'
        reference.write_text(json.dumps({'runs': {'reference-off': {
            'tsv_sha256': digest(baseline), 'output': read_replay(baseline)['output']}}}))
        return binary, corpus, manifest, reference, root / 'output'

    def replay_stub(self, after):
        def replay(command, *, stdout, stderr, check, timeout):
            self.assertTrue(check)
            self.assertGreater(timeout, 0)
            self.assertNotIn('--diagnostic-native-partial-cues', command)
            self.assertNotIn('--diagnostic-cue-free-lane-reassignment', command)
            enabled = '--diagnostic-direct-evidence-retention' in command
            stdout.write(after if enabled else replay_text())
            if enabled:
                for kind in ('candidate', 'outcome', 'midi-event'):
                    path = Path(command[command.index('--' + kind + '-trace') + 1])
                    if kind == 'outcome':
                        rows = outcome_rows()
                    elif kind == 'candidate':
                        rows = [dict(sample=row['sample'], note='42') for row in outcome_rows()]
                    else:
                        rows = [dict(sample='127', kind='on', note='42', voice_id='8'),
                                dict(sample='191', kind='off', note='42', voice_id='8')]
                    with path.open('w') as stream:
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


if __name__ == '__main__':
    unittest.main()
