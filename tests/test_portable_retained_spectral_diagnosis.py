import csv
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_portable_evidence_retention_trial as fixtures
from tools.portable_retained_spectral_diagnosis import FIELDS, FLAG, read_decisions, run


def decisions():
    rows = []
    for tick in (1, 2, 3):
        for ordinal, note in enumerate((42, 48)):
            primary = 2 if ordinal == 0 else 0
            ordinary = 0 if ordinal == 0 else 2
            if tick == 2:
                primary, ordinary = ordinary, primary
            pinned = (ordinal == 0) == (tick == 2)
            rows.append(dict(sample=tick * 64 - 1, tick=tick, note=note,
                selected_count=2, ordinal=ordinal, ordinary_valid=1,
                ordinary_primary=ordinary, retained_primary=primary,
                pin_mask=1 if pinned else 0, playable=5,
                prior_active=int(tick != 3), prior_committed=1,
                prior_primary=ordinary, prior_mask=1 << ordinary,
                prior_midi=1 << ordinary, prior_spectral=1 << ordinary,
                final_primary=primary, final_mask=1 << primary, rendered_mask=1 << primary))
    return rows


def write_trace(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def metadata(rows=6, *, truncated=0, decimation=1):
    return (f'm3_replay: assignment_trace rows={rows} cap=500000 truncated={truncated} '
            f'sampled_frames=3 decimation={decimation}\n')


class PortableRetainedSpectralDiagnosisTests(unittest.TestCase):
    def fixture(self, root):
        text = fixtures.replay_text(target=1)
        args = fixtures.PortableEvidenceRetentionTrialTests().fixture(root, baseline_text=text)
        reference = args[3]
        saved = json.loads(reference.read_text())
        saved['runs']['trial-on'] = saved['runs'].pop('reference-off')
        saved['comparison'] = dict(lost_labels=[55], changed_labels=[dict(
            label_index=55, midi_note=42, string_mask=1, labeled=3,
            baseline_matched=3, current_matched=1, matched_delta=-2)])
        reference.write_text(json.dumps(saved))
        return args, text

    def stub(self, text):
        def replay(command, *, stdout, stderr, check, timeout):
            self.assertTrue(check)
            self.assertGreater(timeout, 0)
            self.assertEqual([arg for arg in command if arg.startswith('--diagnostic-')], [FLAG])
            self.assertEqual(command.count('--retained-assignment-trace'), 1)
            self.assertNotIn('--candidate-trace', command)
            self.assertNotIn('--midi-event-trace', command)
            stdout.write(text)
            stderr.write(metadata())
            write_trace(Path(command[command.index('--retained-assignment-trace') + 1]), decisions())
        return replay

    def test_one_identical_on_replay_keeps_every_peer_and_reports_local_displacement(self):
        with tempfile.TemporaryDirectory() as directory:
            args, text = self.fixture(Path(directory))
            with patch('tools.portable_retained_spectral_diagnosis.subprocess.run',
                       side_effect=self.stub(text)) as replay:
                run(*args)
            self.assertEqual(replay.call_count, 1)
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertEqual(report['state'], 'completed')
            self.assertTrue(report['rejected_on_trial_bit_identical'])
            self.assertFalse(report['installed_output_changed'])
            self.assertFalse(report['runtime_rule_changed'])
            self.assertFalse(report['promotion_accepted'])
            self.assertIn('not OFF counterfactual', report['interpretation'])
            diagnosis = report['diagnosis']
            self.assertEqual(diagnosis['totals']['changed_decisions'], 3)
            self.assertEqual(diagnosis['totals']['changed_unpinned_active_committed_observations'], 2)
            label = diagnosis['lost_labels'][0]
            self.assertEqual(label['observations'], dict(selected_at_changed_decisions=3,
                ordinary_expected_to_other=2, ordinary_other_to_expected=1,
                expected_to_other_unpinned_incumbent=1,
                final_render_contains_expected=1, final_render_exact_expected=1))
            self.assertEqual(len(label['expected_to_other_examples'][0]['selected_peers']), 2)
            self.assertEqual(diagnosis['largest_recorded_loss_label'], 55)
            self.assertFalse((args[-1] / 'retained-assignment.tsv').exists())
            with gzip.open(args[-1] / report['trace']['file'], 'rt') as stream:
                saved = list(csv.DictReader(stream, delimiter='\t'))
            self.assertEqual([{key: int(value) for key, value in row.items()} for row in saved], decisions())

    def test_output_drift_fails_before_attribution(self):
        for drift in ('\n', 'changed fingerprint'):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                args, text = self.fixture(Path(directory))
                text = text + drift if drift == '\n' else text.replace('0123456789abcdef', 'fedcba9876543210')
                with patch('tools.portable_retained_spectral_diagnosis.subprocess.run',
                           side_effect=self.stub(text)) as replay, patch(
                           'tools.portable_retained_spectral_diagnosis.read_decisions') as parse:
                    with self.assertRaisesRegex(ValueError, 'differs from the rejected trial'):
                        run(*args)
                self.assertEqual(replay.call_count, 1)
                parse.assert_not_called()
                report = json.loads((args[-1] / 'report.json').read_text())
                self.assertEqual(report['state'], 'failed')
                self.assertNotIn('diagnosis', report)

    def test_partial_or_inconsistent_capture_is_rejected(self):
        for defect in ('missing peer', 'duplicate ordinal', 'bad pin', 'bad clock',
                       'wrong count', 'truncated', 'decimated'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                rows, meta = decisions(), metadata()
                if defect == 'missing peer':
                    rows.pop()
                    meta = metadata(5)
                elif defect == 'duplicate ordinal':
                    rows[1]['ordinal'] = 0
                elif defect == 'bad pin':
                    rows[1]['pin_mask'] = 4
                elif defect == 'bad clock':
                    rows[-2]['sample'] = rows[-1]['sample'] = 192
                elif defect == 'wrong count':
                    meta = metadata(5)
                elif defect == 'truncated':
                    meta = metadata(truncated=1)
                else:
                    meta = metadata(decimation=16)
                trace, stderr = root / 'trace.tsv', root / 'replay.stderr'
                write_trace(trace, rows)
                stderr.write_text(meta)
                with self.assertRaises(ValueError):
                    read_decisions(trace, stderr, 192)

    def test_saved_lost_label_identity_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            args, text = self.fixture(Path(directory))
            saved = json.loads(args[3].read_text())
            saved['comparison']['changed_labels'][0]['midi_note'] = 43
            args[3].write_text(json.dumps(saved))
            with patch('tools.portable_retained_spectral_diagnosis.subprocess.run',
                       side_effect=self.stub(text)):
                with self.assertRaisesRegex(ValueError, 'Recorded lost label changed'):
                    run(*args)


if __name__ == '__main__':
    unittest.main()
