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
from tools.portable_suppressed_adjacent_admission_trace import (
    ANCHORS, CASE, CONDITIONS, DATASET, WINDOW, diagnose, run, validate_reference)
from tools.suppressed_admission_observation import ADMISSION_FIELDS, admission_peers


REFERENCE = Path(__file__).resolve().parents[1] / 'docs/recovery/suppressed-adjacent-admission-trace-references-20261115.json'


def cell(note=39, tick=1, **changes):
    row = dict.fromkeys(ADMISSION_FIELDS, 0)
    row.update(note=note, tick=tick, peer=128, phase_cents=-90.5,
               selector_best=-0.215, required=240)
    row.update(changes)
    return ':'.join(str(row[key]) for key in ADMISSION_FIELDS)


class SuppressedAdjacentAdmissionTraceTests(unittest.TestCase):
    def test_parser_preserves_signed_terms_and_unknown_observations(self):
        for missing in (None, ''):
            self.assertIsNone(admission_peers(missing, tick=1))
        peers = admission_peers(cell() + ',' + cell(40, selector_pool=1), tick=1)
        self.assertEqual(set(peers), {39, 40})
        self.assertEqual(peers[39]['selector_best'], -0.215)
        self.assertEqual(peers[39]['phase_cents'], -90.5)
        self.assertEqual(peers[39]['peer'], 128)

    def test_parser_rejects_stale_duplicate_malformed_and_nonfinite_values(self):
        for packed in (cell(tick=2), cell()+','+cell(), cell()+':0',
                       cell(enabled=2), cell(prior_midi=256), cell(peer=129),
                       cell(phase_cents='nan'), cell(selector_raw='inf')):
            with self.subTest(packed=packed), self.assertRaises(ValueError):
                admission_peers(packed, tick=1)

    def test_diagnosis_keeps_prior_stage_and_complete_selected_costs(self):
        frames, assignments = [], []
        for sample in range(63, 256, 64):
            tick = (sample+1)//64
            peers = admission_peers(','.join(cell(n, tick, raw_before=1,
                raw_after=int(sample != 191), qualifies=1) for n in (39, 40, 52)), tick=tick)
            frames.append(dict(sample=sample, admission_peers=peers))
            assignments.append(dict(sample=str(sample), observed='1', note='52',
                lane_totals='79,-1,26,188,-1,-1,-1,-1', joint_cost='105'))
        with patch('tools.portable_suppressed_adjacent_admission_trace.ANCHORS', (191,)):
            result = diagnose(assignments, frames, CASE)
            self.assertEqual(result['counts']['39']['filtered'], 1)
            anchor = result['anchors']['191']
            self.assertEqual(anchor['prior']['sample'], 127)
            self.assertEqual(anchor['current']['complete_selected_assignments'], [assignments[2]])
            self.assertEqual(result['state_change_count'], 3)
            frames[1]['admission_peers'] = None
            with self.assertRaisesRegex(ValueError, 'Missing watched'):
                diagnose(assignments, frames, CASE)

    def test_fixed_selection_and_provenance_are_required_before_capture(self):
        reference = json.loads(REFERENCE.read_text())
        manifest = dict(source=reference['source'], files=reference['inputs'])
        validate_reference(reference, manifest)
        for change in (lambda r: r.update(window=[0, 192]),
                       lambda r: r['source'].update(input_release='other'),
                       lambda r: r['inputs']['physical-long.tsv'].update(sha256='0'*64),
                       lambda r: r['replay_references']['current-on'].pop('outcome_sha256'),
                       lambda r: r['replay_references'].pop(CONDITIONS[1][0])):
            altered = copy.deepcopy(reference)
            change(altered)
            with self.assertRaises(ValueError):
                validate_reference(altered, manifest)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'manifest.json'
            path.write_text(json.dumps(manifest))
            with patch('tools.portable_suppressed_adjacent_admission_trace.capture') as mocked:
                run(Path('binary'), Path('corpus'), path, REFERENCE, Path(directory)/'output')
            self.assertEqual(mocked.call_args.kwargs['conditions'], CONDITIONS)
            self.assertEqual(mocked.call_args.kwargs['cases'], (CASE,))
            self.assertEqual(mocked.call_args.kwargs['window'](CASE), WINDOW)
            self.assertIs(mocked.call_args.kwargs['diagnose'], diagnose)

    def test_paired_capture_preserves_each_saved_output_and_current_outcome(self):
        helper = shared_tests.PortablePendingStringTraceTests()
        for drift in (None, 'midi', 'outcome-always'):
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
                refs['current-on']['outcome_sha256'] = digest(saved)
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
                    self.assertTrue(report['runs']['current-on-label53']['saved_outcome_bit_identical'])


if __name__ == '__main__':
    unittest.main()
