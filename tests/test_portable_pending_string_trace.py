import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_assignment_cost_analysis import cost_row, outcome_row
from tests.test_portable_evidence_retention_trial import PortableEvidenceRetentionTrialTests, replay_text
from tests.test_portable_midi_lane_trace import candidates, event, write_events
from tests.test_portable_routing_trace import write_rows
from tools.frozen_cue_corpus_gate import read_replay
from tools.midi_lifecycle_analysis import read_events, summarize
from tools.portable_assignment_trace import digest
from tools.portable_pending_string_trace import explain_frames, run


CASES = tuple(dict(label_index=i, midi_note=42, string_mask=1,
                  start_sample=0, end_sample=192) for i in (53, 54, 55))


class PortablePendingStringTraceTests(unittest.TestCase):
    def fixture(self, root):
        lines = replay_text().splitlines(keepends=True)
        labels = list(csv.DictReader(lines[2:], delimiter='\t'))
        for row in labels:
            if int(row['label_index']) in (53, 54):
                row['midi_note'] = '42'
        stream = io.StringIO()
        stream.write(''.join(lines[:2]))
        writer = csv.DictWriter(stream, fieldnames=labels[0], delimiter='\t')
        writer.writeheader()
        writer.writerows(labels)
        text = stream.getvalue()
        args = PortableEvidenceRetentionTrialTests().fixture(root, baseline_text=text)
        parsed = read_replay(root / 'baseline.tsv')
        refs = {}
        for policy, start in (('current-on', 64), ('trial-on', 32)):
            path = root / (policy + '.tsv')
            write_events(path, [event(start, 'on', 42, 0), event(191, 'off', 42, 1)])
            held = summarize(read_events(path, sample_count=192, transition_count=2),
                             parsed['labels'], sample_count=192, sample_rate=96000)
            refs[policy] = dict(tsv_sha256=digest(root / 'baseline.tsv'),
                midi_sha256=digest(path), output=parsed['output'], sample_count=192,
                sample_rate=96000, held_labels={str(row['label_index']): row
                    for row in held['labels'] if row['label_index'] in (53, 54, 55)})
        args[3].write_text(json.dumps(dict(replay_references=refs)))
        return args, text

    def execute(self, args, text, *, drift=None):
        calls = 0

        def replay(command, *, stdout, stderr, check, timeout):
            nonlocal calls
            calls += 1
            self.assertTrue(check)
            self.assertGreater(timeout, 0)
            self.assertIn('--diagnostic-spectral-lane-collision', command)
            trial = '--diagnostic-pending-string-reservation' in command
            self.assertEqual(int(command[command.index('--candidate-trace-note') + 1]), 42)
            stdout.write(text + ('\n' if drift == 'output' else ''))
            write_rows(Path(command[command.index('--candidate-trace') + 1]), candidates(42))
            outcomes = [outcome_row((42,), sample=s) for s in (63, 127, 191)]
            if drift == 'outcome' and calls == 2:
                outcomes[0]['quiet'] = '1'
            write_rows(Path(command[command.index('--outcome-trace') + 1]), outcomes)
            assignments = [dict(cost_row(42, sample=s), prior_attack_ticks='2',
                                attack_required='2', allocation_preview='0') for s in (63, 127, 191)]
            if drift == 'missing-peer':
                assignments.pop(1)
            write_rows(Path(command[command.index('--assignment-trace') + 1]), assignments)
            write_events(Path(command[command.index('--midi-event-trace') + 1]),
                         [event(32 if trial else 64, 'on', 42, 0), event(191, 'off', 42, 1)])

        with patch('tools.portable_pending_string_trace.CASES', CASES), patch(
                'tools.portable_pending_string_trace.window_for', return_value=(0, 192)), patch(
                'tools.portable_pending_string_trace.subprocess.run', side_effect=replay) as mocked:
            run(*args)
        return mocked

    def test_six_captures_preserve_both_references_and_retain_compressed_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            args, text = self.fixture(Path(directory))
            mocked = self.execute(args, text)
            self.assertEqual(mocked.call_count, 6)
            report = json.loads((args[-1] / 'report.json').read_text())
            self.assertEqual(report['state'], 'completed')
            self.assertTrue(report['saved_references_bit_identical'])
            self.assertTrue(report['repeated_policy_streams_bit_identical'])
            self.assertFalse(report['runtime_rule_changed'])
            self.assertFalse(report['promotion_accepted'])
            for stem, result in report['runs'].items():
                self.assertEqual(result['diagnosis']['counts']['frames'], 3)
                self.assertTrue(result['assignment_costs']['native_joint_decisions_reproduced'])
                for trace in result['traces'].values():
                    path = args[-1] / stem / trace['file']
                    self.assertEqual(digest(path), trace['sha256'])
                    self.assertFalse(path.with_suffix('').exists())

    def test_changed_output_capture_or_incomplete_assignment_fails_closed(self):
        for drift, message in (('output', 'saved output or raw MIDI'),
                               ('outcome', 'complete MIDI or outcome'),
                               ('missing-peer', 'Incomplete selected assignment peers')):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                args, text = self.fixture(Path(directory))
                with self.assertRaisesRegex(ValueError, message):
                    self.execute(args, text, drift=drift)
                report = json.loads((args[-1] / 'report.json').read_text())
                self.assertEqual(report['state'], 'failed')
                self.assertTrue(report['final'])

    def test_changed_saved_hold_is_rejected_even_with_identical_raw_output(self):
        with tempfile.TemporaryDirectory() as directory:
            args, text = self.fixture(Path(directory))
            reference = json.loads(args[3].read_text())
            reference['replay_references']['current-on']['held_labels']['53']['exact_held_samples'] += 1
            args[3].write_text(json.dumps(reference))
            with self.assertRaisesRegex(ValueError, 'Saved held-note measurement changed'):
                self.execute(args, text)

    def test_preview_and_ready_infeasible_are_distinct_observations(self):
        frames = [dict(sample=s, candidate_state=dict(selection=4, active=0),
                       routing=dict(midi_after=0, capacity_blocked=0)) for s in (63, 127)]
        rows = [dict(cost_row(42, active=0, sample=s), allocation_preview=str(preview),
                     prior_attack_ticks=str(1-preview), attack_required='2', valid=str(preview))
                for s, preview in ((63, 1), (127, 0))]
        diagnosis, transitions = explain_frames(frames, rows, CASES[0])
        self.assertEqual(diagnosis['counts']['preview'], 1)
        self.assertEqual(diagnosis['counts']['ready_infeasible'], 1)
        self.assertEqual(diagnosis['counts']['active'], 0)
        self.assertEqual(len(transitions), 2)


if __name__ == '__main__':
    unittest.main()
