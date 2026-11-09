import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_portable_evidence_retention_trial import outcome_rows, replay_text
from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_assignment_trace import digest
from tools.portable_routing_trace import ROUTING_FIELDS, outcome_window, run, summarize_routing


def routing_rows():
    rows = []
    for tick in range(1, 4):
        route = dict.fromkeys(ROUTING_FIELDS, 0)
        if tick > 1:
            route.update(tick=tick, render_observed=1, assigned_mask=1,
                         continuity_mask=2, desired_mask=2, pruned_mask=2,
                         midi_before=2, midi_after=2)
        rows.append(dict(sample=str(tick * 64 - 1), tick=str(tick), note='52',
                         **{'route_' + key: str(value) for key, value in route.items()}))
    return rows


def snapshots():
    rows = outcome_rows()
    for row in rows:
        row.update(labels='54:52:2', candidates='', matched_labels='54',
                   voices='52:52:1:0:10:1:0:2')
    return rows


def write_rows(path, rows, columns=None):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns or rows[0], delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


class PortableRoutingTraceTests(unittest.TestCase):
    def test_stage_clocks_distinguish_unobserved_from_zero(self):
        result = summarize_routing(routing_rows(), snapshots(), [], note=52,
                                   label_index=54, start=0, end=192)
        self.assertEqual(result[0]['routing']['tick'], 0)
        self.assertEqual(result[1]['routing']['tick'], 2)
        self.assertEqual(result[1]['routing']['continuity_observed'], 0)
        self.assertTrue(result[1]['label_matched'])
        self.assertEqual(result[1]['midi_events'], [])
        for field, value in (('route_tick', '1'), ('tick', '1'), ('note', '41')):
            rows = routing_rows()
            rows[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                summarize_routing(rows, snapshots(), [], note=52,
                                  label_index=54, start=0, end=192)

    def test_missing_or_duplicate_capture_is_rejected(self):
        for candidates, outcomes in ((routing_rows()[:-1], snapshots()),
                (routing_rows() + [routing_rows()[0]], snapshots()),
                (routing_rows(), snapshots()[:-1]),
                (routing_rows(), snapshots() + [snapshots()[0]])):
            with self.subTest(candidates=len(candidates), outcomes=len(outcomes)):
                with self.assertRaises(ValueError):
                    summarize_routing(candidates, outcomes, [], note=52,
                                      label_index=54, start=0, end=192)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'outcome.tsv'
            write_rows(path, snapshots())
            self.assertEqual(outcome_window(path, 192, 64, 192), snapshots()[1:])
            write_rows(path, snapshots()[1:])
            with self.assertRaisesRegex(ValueError, 'full outcome capture'):
                outcome_window(path, 192, 64, 192)

    def fixture(self, root):
        corpus = root / 'corpus'
        corpus.mkdir()
        for name in ('ordinary.wav', 'ordinary.tsv', 'calibration.m3cb', 'templates.tsv'):
            (corpus / name).write_text(name)
        manifest = root / 'manifest.json'
        manifest.write_text(json.dumps({'files': {
            path.name: {'sha256': digest(path)} for path in corpus.iterdir()}}))
        binary = root / 'replay'
        binary.write_text('mocked replay binary')
        before = replay_text().replace('54\t0\t192\t60\t1', '54\t0\t192\t52\t2')
        after = replay_text(target=2).replace('54\t0\t192\t60\t1', '54\t0\t192\t52\t2')
        reference = root / 'reference.json'
        runs = {}
        for stem, text in (('reference-off', before), ('trial-on', after)):
            path = root / (stem + '.tsv')
            path.write_text(text)
            runs[stem] = dict(tsv_sha256=digest(path), output=read_replay(path)['output'])
        reference.write_text(json.dumps(dict(runs=runs)))
        return (binary, corpus, manifest, reference, root / 'output'), (before, after)

    def replay_stub(self, texts):
        def replay(command, *, stdout, stderr, check, timeout):
            self.assertTrue(check)
            self.assertGreater(timeout, 0)
            self.assertNotIn('--diagnostic-native-partial-cues', command)
            self.assertNotIn('--diagnostic-direct-evidence-retention', command)
            enabled = '--diagnostic-projection-preview-admission' in command
            self.assertEqual(enabled, Path(stdout.name).parent.name == 'trial-on')
            self.assertEqual(command[command.index('--candidate-trace-note') + 1], '52')
            stdout.write(texts[int(enabled)])
            for kind, rows in (('candidate', routing_rows()), ('outcome', snapshots()),
                               ('midi-event', [])):
                path = Path(command[command.index('--' + kind + '-trace') + 1])
                write_rows(path, rows, None if rows else ['sample', 'kind', 'note', 'voice_id'])
        return replay

    def test_both_historical_outputs_are_required_and_do_not_accept_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            args, texts = self.fixture(Path(directory))
            with patch('tools.portable_routing_trace.WINDOW', (0, 192)), patch(
                    'tools.portable_routing_trace.subprocess.run',
                    side_effect=self.replay_stub(texts)) as replay:
                run(*args)
            result = json.loads((args[4] / 'report.json').read_text())
            self.assertEqual(replay.call_count, 2)
            self.assertEqual(result['state'], 'completed')
            self.assertFalse(result['promotion_accepted'])
            self.assertFalse(result['runtime_rule_changed'])
            self.assertFalse(result['installed_output_changed'])
            for stem, retained in result['runs'].items():
                self.assertTrue(retained['reference_bit_identical'])
                self.assertEqual(len(retained['routing_frames']), 3)
                for kind, trace in retained['traces'].items():
                    self.assertEqual(digest(args[4] / stem / trace['file']), trace['sha256'])
                    self.assertFalse((args[4] / stem / (kind + '.tsv')).exists())

    def test_hash_drift_stops_diagnosis_for_either_mode(self):
        for index, stem in enumerate(('reference-off', 'trial-on')):
            with self.subTest(stem=stem), tempfile.TemporaryDirectory() as directory:
                args, texts = self.fixture(Path(directory))
                changed = list(texts)
                changed[index] += '\n'
                with patch('tools.portable_routing_trace.WINDOW', (0, 192)), patch(
                        'tools.portable_routing_trace.subprocess.run',
                        side_effect=self.replay_stub(changed)) as replay:
                    with self.assertRaisesRegex(ValueError, stem + ' differs'):
                        run(*args)
                self.assertEqual(replay.call_count, index + 1)
                result = json.loads((args[4] / 'report.json').read_text())
                self.assertEqual(result['state'], 'failed')
                self.assertTrue(result['final'])
                self.assertFalse(result['promotion_accepted'])
                self.assertNotIn('routing_differences', result)


if __name__ == '__main__':
    unittest.main()
