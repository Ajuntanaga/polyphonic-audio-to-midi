import copy
from functools import partial
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tests import test_portable_pending_string_trace as shared
from tests.test_candidate_outcome_analysis import candidate, frame, stream
from tools.candidate_outcome_analysis import compare_streams
from tools.portable_pending_string_trace import run as capture
from tools.portable_completion_window_retention_trace import (
    CASE, CONDITIONS, DATASET, WINDOW, CompleteOutcomes, WrongNoteChanges,
    run, validate_reference)


REFERENCE = (Path(__file__).resolve().parents[1] /
             'docs/recovery/completion-window-retention-trace-references-20261115.json')
WRONG = '39:39:1:1:6:0:0:1'


def totals(labeled, wrong):
    return dict(labeled=labeled, matched=0, false_positive_voices=wrong,
                false_wrong_note_voices=wrong, false_wrong_string_voices=0,
                false_gap_voices=0)


def six_added():
    a = [frame(s, '3:40:7', candidates=candidate(39)) for s in range(100, 800, 100)]
    b = [frame(s, '3:40:7', voices=WRONG if s > 100 else '',
               candidates=candidate(39)) for s in range(100, 800, 100)]
    return stream(*a), stream(*b)


class CompletionWindowRetentionTraceTests(unittest.TestCase):
    def test_all_six_same_identity_additions_keep_prior_paired_context(self):
        observer = WrongNoteChanges()
        result = compare_streams(*six_added(), totals(7, 0), totals(7, 6),
                                 observe_frame=observer)
        self.assertEqual(observer.counts, {'added': 6, 'removed': 0})
        self.assertEqual(len(observer.frames), 6)
        self.assertEqual(result['trial']['wrong_note'], 6)
        for row, sample in zip(observer.frames, range(200, 800, 100)):
            self.assertEqual(row['sample'], sample)
            self.assertEqual(row['added'], [dict(identity=(39, 39, 1), count=1)])
            self.assertEqual(row['preceding_control']['sample'], sample-100)
            self.assertEqual(row['preceding_trial']['sample'], sample-100)
            self.assertEqual(row['trial']['voices'][0][4], 6)
            self.assertIn(39, row['trial']['candidates'])

    def test_multiplicity_and_removed_wrong_notes_are_not_hidden_by_net_count(self):
        observer = WrongNoteChanges()
        a = stream(frame(100, '3:40:7', voices=','.join([WRONG]*3)))
        b = stream(frame(100, '3:40:7', voices=WRONG+',46:46:1:1:6:0:0:1'))
        compare_streams(a, b, totals(1, 3), totals(1, 2), observe_frame=observer)
        self.assertEqual(observer.counts, {'added': 1, 'removed': 2})
        self.assertEqual(observer.frames[0]['removed'][0]['count'], 2)
        self.assertIsNone(observer.frames[0]['preceding_control'])

    def test_misaligned_frames_are_rejected_before_observation(self):
        observer = Mock()
        with self.assertRaises(ValueError):
            compare_streams(stream(frame(100)), stream(frame(101)), observe_frame=observer)
        observer.assert_not_called()

    def test_complete_outcomes_survive_source_removal_and_reconcile_saved_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            refs = {'current-on': {'output': totals(7, 0)},
                    CONDITIONS[1][0]: {'output': totals(7, 6)}}
            observer = CompleteOutcomes(root, refs)
            paths = [root/'current.tsv', root/'trial.tsv']
            texts = [s.getvalue() for s in six_added()]
            for path, text in zip(paths, texts):
                path.write_text(text)
            with self.assertRaisesRegex(ValueError, 'before trial'):
                observer(CONDITIONS[1][0], paths[1])
            current = observer('current-on', paths[0])
            paths[0].unlink()
            result = observer(CONDITIONS[1][0], paths[1])
            self.assertEqual(result['wrong_note_changes'], {'added': 6, 'removed': 0})
            self.assertEqual(len(result['changed_wrong_note_frames']), 6)
            self.assertFalse(result['truncated'])
            for record, text in zip((current, result), texts):
                with gzip.open(root/record['complete_outcome']['file'], 'rt') as saved:
                    self.assertEqual(saved.read(), text)
            with self.assertRaisesRegex(ValueError, 'repeated'):
                observer(CONDITIONS[1][0], paths[1])

    def test_trial_totals_must_match_saved_replay_before_result_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            refs = {'current-on': {'output': totals(7, 0)},
                    CONDITIONS[1][0]: {'output': totals(7, 5)}}
            observer = CompleteOutcomes(root, refs)
            for policy, text in zip(refs, six_added()):
                path = root/(policy+'.tsv')
                path.write_text(text.getvalue())
                if policy == 'current-on':
                    observer(policy, path)
                else:
                    with self.assertRaisesRegex(ValueError, 'trace/report mismatch'):
                        observer(policy, path)
                    self.assertFalse((root/(policy+'-complete-outcome.tsv.gz')).exists())

    def test_fixed_provenance_saved_clocks_and_current_outcome_gate(self):
        reference = json.loads(REFERENCE.read_text())
        manifest = copy.deepcopy(dict(source=reference['source'], files=reference['inputs']))
        validate_reference(reference, manifest)
        self.assertNotIn('outcome_sha256', reference['replay_references'][CONDITIONS[1][0]])
        for change in (lambda r: r.update(window=[0, 192]),
                       lambda r: r['source'].update(input_release='other'),
                       lambda r: r['inputs'][DATASET+'.tsv'].update(sha256='0'*64),
                       lambda r: r['replay_references']['current-on'].pop('outcome_sha256'),
                       lambda r: r['replay_references'][CONDITIONS[1][0]].update(sample_count=192)):
            altered = copy.deepcopy(reference)
            change(altered)
            with self.assertRaises(ValueError):
                validate_reference(altered, manifest)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'manifest.json'
            path.write_text(json.dumps(manifest))
            with patch('tools.portable_completion_window_retention_trace.capture') as mocked:
                run(Path('binary'), Path('corpus'), path, REFERENCE, Path(directory)/'output')
            options = mocked.call_args.kwargs
            self.assertEqual(options['conditions'], CONDITIONS)
            self.assertEqual(options['cases'], (CASE,))
            self.assertEqual(options['dataset'], DATASET)
            self.assertEqual(options['window'](CASE), WINDOW)
            self.assertIsInstance(options['observe_outcome'], CompleteOutcomes)

    def test_capture_observer_runs_after_saved_output_midi_and_hold_gates(self):
        helper = shared.PortablePendingStringTraceTests()
        for drift in (None, 'output', 'midi', 'held'):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                args, text = helper.fixture(Path(directory))
                if drift == 'held':
                    ref = json.loads(args[3].read_text())
                    ref['replay_references']['current-on']['held_labels']['53']['exact_held_samples'] += 1
                    args[3].write_text(json.dumps(ref))
                observer = Mock(return_value={'snapshot_only': True})
                runner = partial(capture, cases=(shared.CASES[0],), observe_outcome=observer)
                if drift:
                    with self.assertRaises(ValueError):
                        helper.execute(args, text, runner=runner, drift=drift)
                    observer.assert_not_called()
                else:
                    helper.execute(args, text, runner=runner)
                    self.assertEqual([call.args[0] for call in observer.call_args_list],
                                     ['current-on', 'trial-on'])
                    report = json.loads((args[-1]/'report.json').read_text())
                    self.assertTrue(all(row['complete_outcome_diagnosis']['snapshot_only']
                                        for row in report['runs'].values()))


if __name__ == '__main__':
    unittest.main()
