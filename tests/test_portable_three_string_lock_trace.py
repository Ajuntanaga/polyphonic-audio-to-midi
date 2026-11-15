import copy
from functools import partial
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_portable_pending_string_trace as shared_tests
from tests.test_assignment_cost_analysis import outcome_row
from tests.test_portable_routing_trace import write_rows
from tools.portable_assignment_trace import digest
from tools.portable_pending_string_trace import run as capture
from tools.portable_three_string_lock_trace import (
    CASE, CONDITIONS, DATASET, INTERPRETATION, SUSTAIN_WINDOW, chronology,
    run, sustain_chronology, validate_reference)


def observations(sample, *, fine=1, committed=1, assigned=1, routed=1,
                 route_observed=True, matched=False):
    state = dict(selection=4, active=1, fine_valid=1, fine_mask=fine,
                 committed_mask=committed, assigned_mask=assigned)
    frame = dict(sample=sample, candidate_state=state,
        routing=dict(render_observed=int(route_observed), continuity_observed=0, midi_after=routed),
        matched_labels=[3] if matched else [])
    row = {key: '0' for key in ('prior_active', 'prior_primary', 'dp_primary',
        'group_before', 'group_proposal', 'group_after', 'fine_pending_mask',
        'profile_fit_observed', 'profile_primary_error', 'profile_mixture_error',
        'ordinal', 'prior_midi')}
    row.update(sample=str(sample), note='40', observed='1', valid='1', playable='7',
        final_mask=str(assigned), rendered_mask=str(assigned), render_observed='1',
        fine_valid='1', fine_mask=str(fine),
        profile_first_pass_reasons=','.join(['0']*8),
        profile_first_pass_alpha=','.join(['-1']*8),
        profile_first_pass_errors=','.join(['-1']*8))
    return frame, row


class ThreeStringLockTraceTests(unittest.TestCase):
    def test_stage_order_preserves_prelabel_state_and_unobserved_routes(self):
        label = dict(label_index=3, midi_note=40, string_mask=7, start_sample=64, end_sample=256)
        pairs = [observations(63, route_observed=False, routed=7),
                 observations(127, fine=7),
                 observations(191, fine=7, committed=7, assigned=7, routed=7, matched=True),
                 observations(255, fine=15, committed=15, assigned=15, routed=15)]
        result = chronology([row for _, row in pairs], [frame for frame, _ in pairs], label)
        stages = result['stages']
        self.assertEqual(stages['candidate_active']['first_in_window']['offset_from_label_start'], -1)
        self.assertEqual(stages['fine_exact_mask']['first_in_label']['sample'], 127)
        self.assertEqual(stages['assignment_rendered_exact_mask']['first_in_label']['sample'], 191)
        self.assertEqual(stages['route_midi_exact_mask']['first_in_window']['sample'], 191)
        self.assertEqual(stages['route_midi_exact_mask']['unobserved'], 1)
        self.assertEqual(stages['route_midi_exact_mask']['true'], 1)
        self.assertEqual(stages['fine_exact_mask']['label_true'], 2)
        self.assertEqual(stages['snapshot_exact_label_match']['unobserved'], 1)
        self.assertEqual(result['label_frames'], 3)

    def test_absent_candidate_and_assignment_do_not_invent_mask_measurements(self):
        frame, _ = observations(127)
        frame['candidate_state'] = None
        frame['routing']['render_observed'] = 0
        result = chronology([], [frame], dict(label_index=3, midi_note=40,
                            string_mask=7, start_sample=64, end_sample=192))
        self.assertEqual(result['stages']['candidate_active']['false'], 1)
        for name in ('fine_exact_mask', 'assignment_final_exact_mask', 'route_midi_exact_mask'):
            self.assertEqual(result['stages'][name]['unobserved'], 1)
            self.assertIsNone(result['stages'][name]['first_in_label'])

    def test_saved_reference_rejects_wrong_selection_hash_or_input_provenance(self):
        path = Path(__file__).resolve().parents[1] / 'docs/recovery/three-string-lock-references-20261115.json'
        reference = json.loads(path.read_text())
        manifest = dict(source=reference['source'], files=reference['inputs'])
        validate_reference(reference, manifest)
        changes = [lambda r: r.update(dataset='ordinary'),
                   lambda r: r['replay_references']['current-on'].pop('outcome_sha256'),
                   lambda r: r['source'].update(input_release='different'),
                   lambda r: r['inputs']['physical-long.tsv'].update(sha256='0'*64),
                   lambda r: r['replay_references']['current-on']['held_labels']['3'].update(
                       first_exact_hold_delay_samples=0)]
        for change in changes:
            with self.subTest(change=change):
                altered = copy.deepcopy(reference)
                change(altered)
                with self.assertRaises(ValueError):
                    validate_reference(altered, manifest)

    def test_sustain_requires_its_fixed_window_and_preserves_complete_references(self):
        root = Path(__file__).resolve().parents[1]
        path = root / 'docs/recovery/three-string-sustain-references-20261115.json'
        reference = json.loads(path.read_text())
        initial = json.loads((root / 'docs/recovery/three-string-lock-references-20261115.json').read_text())
        manifest = dict(source=reference['source'], files=reference['inputs'])
        validate_reference(reference, manifest, phase='sustain')
        self.assertEqual(reference['replay_references'], initial['replay_references'])
        with self.assertRaises(ValueError):
            validate_reference(reference, manifest)
        reference['window'][0] += 64
        with self.assertRaises(ValueError):
            validate_reference(reference, manifest, phase='sustain')

    def test_sustain_keeps_all_route_changes_and_unobserved_is_not_zero(self):
        pairs = [observations(63 + 64*i, fine=7, committed=7, assigned=7,
                              routed=7 if i % 2 == 0 else 6) for i in range(36)]
        pairs[-1][0]['routing']['render_observed'] = 0
        label = dict(label_index=3, midi_note=40, string_mask=7, start_sample=0, end_sample=2400)
        result = sustain_chronology([r for _, r in pairs], [f for f, _ in pairs], label)
        self.assertEqual(result['route_change_count'], 35)
        changes = result['route_changes']
        self.assertEqual(changes[0]['before_mask'], 7)
        self.assertEqual(changes[0]['after_mask'], 6)
        self.assertEqual(changes[0]['before']['frame']['sample'], 63)
        self.assertEqual(changes[0]['after']['target_assignment']['final_mask'], '7')
        self.assertIsNone(changes[-1]['after_mask'])

    def test_sustain_run_selects_one_unchanged_current_on_capture(self):
        path = Path(__file__).resolve().parents[1] / 'docs/recovery/three-string-sustain-references-20261115.json'
        reference = json.loads(path.read_text())
        with tempfile.TemporaryDirectory() as directory, patch('tools.portable_three_string_lock_trace.capture') as mocked:
            root = Path(directory)
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(dict(source=reference['source'], files=reference['inputs'])))
            run(root / 'binary', root / 'corpus', manifest, path, root / 'output', phase='sustain')
            kwargs = mocked.call_args.kwargs
            self.assertEqual(mocked.call_count, 1)
            self.assertEqual(kwargs['conditions'], CONDITIONS)
            self.assertEqual(kwargs['cases'], (CASE,))
            self.assertEqual(kwargs['window'](CASE), SUSTAIN_WINDOW)
            self.assertIs(kwargs['diagnose'], sustain_chronology)

    def test_shared_capture_selects_physical_input_and_requires_complete_outcome_identity(self):
        helper = shared_tests.PortablePendingStringTraceTests()
        for drift in (None, 'outcome-always'):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args, text = helper.fixture(root)
                manifest = json.loads(args[2].read_text())
                for suffix in ('.wav', '.tsv'):
                    old, new = 'ordinary'+suffix, DATASET+suffix
                    (args[1]/old).rename(args[1]/new)
                    manifest['files'][new] = manifest['files'].pop(old)
                args[2].write_text(json.dumps(manifest))
                saved_outcome = root/'saved-outcome.tsv'
                write_rows(saved_outcome, [outcome_row((42,), sample=s) for s in (63, 127, 191)])
                reference = json.loads(args[3].read_text())
                reference['replay_references']['current-on']['outcome_sha256'] = digest(saved_outcome)
                args[3].write_text(json.dumps(reference))
                runner = partial(capture, dataset=DATASET, conditions=CONDITIONS,
                                 cases=(shared_tests.CASES[0],), interpretation=INTERPRETATION)
                if drift:
                    with self.assertRaisesRegex(ValueError, 'saved complete outcome'):
                        helper.execute(args, text, runner=runner, drift=drift)
                    continue
                mocked = helper.execute(args, text, runner=runner)
                self.assertEqual(mocked.call_count, 1)
                command = mocked.call_args.args[0]
                self.assertIn(str(args[1]/'physical-long.wav'), command)
                self.assertIn(str(args[1]/'physical-long.tsv'), command)
                report = json.loads((args[-1]/'report.json').read_text())
                self.assertEqual(report['dataset'], DATASET)
                self.assertEqual(report['interpretation'], INTERPRETATION)
                self.assertTrue(report['runs']['current-on-label53']['saved_outcome_bit_identical'])


if __name__ == '__main__':
    unittest.main()
