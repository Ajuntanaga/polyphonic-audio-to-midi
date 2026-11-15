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
from tests.test_portable_suppressed_adjacent_admission_trace import cell
from tools.portable_assignment_trace import digest
from tools.portable_midi_lane_trace import fine_group_observation
from tools.portable_pending_string_trace import run as capture
from tools.portable_qualified_tier_retention_trace import (
    ANCHORS, CASE, CONDITIONS, DATASET, WINDOW, diagnose, run, validate_reference)
from tools.suppressed_admission_observation import admission_peers


REFERENCE = Path(__file__).resolve().parents[1] / 'docs/recovery/qualified-tier-retention-trace-references-20261115.json'


def fine_row(**changes):
    row = dict(fine_group_disposition='accepted', fine_valid='1', fine_mask='40',
        committed_mask='41', ownership_observed='1', fine_group_evaluated='1',
        fine_group_mask='40', fine_group_other_owned='0', fine_group_overlap='0',
        fine_group_allocated='0', fine_group_extra_capacity='3',
        fine_group_owners='52:1:1:41', fine_group_owner_counts='1,0,0,1,0,1,0,0')
    row.update(changes)
    return row


class QualifiedTierRetentionTraceTests(unittest.TestCase):
    def test_named_group_stage_preserves_distinction_and_legacy_unknown(self):
        self.assertIsNone(fine_group_observation({}))
        for disposition in ('accepted', 'missing_primary', 'conflicts_other_owned'):
            parsed = fine_group_observation(fine_row(fine_group_disposition=disposition))
            self.assertEqual(parsed['disposition'], disposition)
            self.assertEqual(parsed['fine_mask'], 40)
            self.assertEqual(parsed['committed_mask'], 41)
            self.assertEqual(parsed['owners'], '52:1:1:41')
        missing = fine_row()
        del missing['fine_group_mask']
        for row in (missing, fine_row(fine_group_disposition='fitted'),
                    fine_row(ownership_observed='2'), fine_row(fine_group_overlap='256')):
            with self.assertRaises(ValueError):
                fine_group_observation(row)

    def test_diagnosis_keeps_primary_stage_prior_tick_and_complete_peers(self):
        frames, assignments = [], []
        for sample in range(WINDOW[0]+63, WINDOW[1], 64):
            tick = (sample+1)//64
            peers = admission_peers(','.join(cell(n, tick, selector_best=-0.215)
                                             for n in (40, 52, 60)), tick=tick)
            frames.append(dict(sample=sample, admission_peers=peers,
                fine_group=fine_group_observation(fine_row()),
                routing=dict(primary_string=3), tracking=dict(active=1)))
            assignments.append(dict(sample=str(sample), observed='1', note='52',
                dp_primary='3', group_before='41', group_proposal='41',
                group_origin='2', group_transition='2', group_after='41',
                lane_totals='79,-1,26,188,-1,-1,-1,-1', joint_cost='105'))
        result = diagnose(assignments, frames, CASE)
        self.assertEqual(result['window_frames'], 12)
        self.assertEqual(result['observed_notes'], [40, 52, 60])
        self.assertEqual(result['fine_group_dispositions'], {'accepted': 12})
        self.assertEqual(result['dp_primary_counts'], {'3': 12})
        for sample in ANCHORS:
            anchor = result['anchors'][str(sample)]
            self.assertEqual(anchor['prior']['sample'], sample-64)
            self.assertEqual(anchor['current']['group']['group_origin'], 2)
            self.assertEqual(anchor['current']['complete_admission_peers'][60]['selector_best'], -0.215)
            self.assertEqual(anchor['current']['complete_selected_assignments'][0]['joint_cost'], '105')
        for mutation in ('fine', 'peer', 'target', 'stage'):
            altered, rows = copy.deepcopy(frames), copy.deepcopy(assignments)
            if mutation == 'fine':
                altered[1]['fine_group'] = None
            elif mutation == 'peer':
                del altered[1]['admission_peers'][60]
            elif mutation == 'target':
                rows.pop(1)
            else:
                del rows[1]['group_origin']
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, KeyError)):
                diagnose(rows, altered, CASE)

    def test_fixed_selection_provenance_and_both_complete_outcomes_are_required(self):
        reference = json.loads(REFERENCE.read_text())
        manifest = dict(source=reference['source'], files=reference['inputs'])
        validate_reference(reference, manifest)
        for change in (lambda r: r.update(window=[0, 192]),
                       lambda r: r['source'].update(input_release='other'),
                       lambda r: r['inputs'][DATASET+'.tsv'].update(sha256='0'*64),
                       lambda r: r['replay_references']['current-on'].pop('outcome_sha256'),
                       lambda r: r['replay_references'][CONDITIONS[1][0]].pop('outcome_sha256')):
            altered = copy.deepcopy(reference)
            change(altered)
            with self.assertRaises(ValueError):
                validate_reference(altered, manifest)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'manifest.json'
            path.write_text(json.dumps(manifest))
            with patch('tools.portable_qualified_tier_retention_trace.capture') as mocked:
                run(Path('binary'), Path('corpus'), path, REFERENCE, Path(directory)/'output')
            self.assertEqual(mocked.call_args.kwargs['conditions'], CONDITIONS)
            self.assertEqual(mocked.call_args.kwargs['cases'], (CASE,))
            self.assertEqual(mocked.call_args.kwargs['dataset'], DATASET)
            self.assertEqual(mocked.call_args.kwargs['window'](CASE), WINDOW)
            self.assertIs(mocked.call_args.kwargs['diagnose'], diagnose)

    def test_paired_capture_rejects_trial_only_outcome_drift(self):
        helper = shared_tests.PortablePendingStringTraceTests()
        for drift in (None, 'output', 'midi', 'outcome-always', 'outcome'):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args, text = helper.fixture(root)
                manifest = json.loads(args[2].read_text())
                for suffix in ('.wav', '.tsv'):
                    old, new = 'ordinary'+suffix, DATASET+suffix
                    (args[1]/old).rename(args[1]/new)
                    manifest['files'][new] = manifest['files'].pop(old)
                args[2].write_text(json.dumps(manifest))
                saved = root/'outcome.tsv'
                write_rows(saved, [outcome_row((42,), sample=s) for s in (63, 127, 191)])
                reference = json.loads(args[3].read_text())
                refs = reference['replay_references']
                refs[CONDITIONS[1][0]] = refs.pop('trial-on')
                for row in refs.values():
                    row['outcome_sha256'] = digest(saved)
                args[3].write_text(json.dumps(reference))
                runner = partial(capture, dataset=DATASET, conditions=CONDITIONS,
                                 cases=(shared_tests.CASES[0],))
                if drift:
                    with self.assertRaisesRegex(ValueError, 'saved output or raw MIDI|saved complete outcome'):
                        helper.execute(args, text, runner=runner, drift=drift,
                                       trial_flag=CONDITIONS[1][1][-1])
                else:
                    mocked = helper.execute(args, text, runner=runner,
                                            trial_flag=CONDITIONS[1][1][-1])
                    self.assertEqual(mocked.call_count, 2)
                    report = json.loads((args[-1]/'report.json').read_text())
                    self.assertTrue(report['saved_references_bit_identical'])
                    for row in report['runs'].values():
                        self.assertTrue(row['saved_outcome_bit_identical'])


if __name__ == '__main__':
    unittest.main()
