import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_vst3_stable_note_corpus as runner
from tools.portable_vst3_process_timing import SCOPE
from tests.test_portable_vst3_corpus_replay import HEADER


class CorpusRunnerTests(unittest.TestCase):
    def exercise(self, fail_timing=False, invalid_second=False, diagnostic=False,
                 batch=False, batch_fault=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'fixture.tsv').write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n0\t80\t60\t1\n')
            source = dict(commit='a'*40, input_release='fixture',
                          input_bundle_sha256='b'*64, original_input_manifest_sha256='c'*64)
            (root / 'manifest.json').write_text(json.dumps({'source': source}))
            (root / 'reference.json').write_text(json.dumps({'datasets': {'fixture': {'current-on': {
                'sample_count': 100, 'sample_rate': 96000}}}}))
            datasets = {'fixture': {}}
            if invalid_second:
                datasets['bad'] = {}
                reference = json.loads((root/'reference.json').read_text())
                reference['datasets']['bad'] = reference['datasets']['fixture']
                (root/'reference.json').write_text(json.dumps(reference))
                (root/'bad.tsv').write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n0\t101\t60\t1\n')
            binary = root / 'binary'
            binary.write_bytes(b'fixture only')
            args = SimpleNamespace(binary=binary, corpus=root, manifest=root/'manifest.json',
                reference=root/'reference.json', source_sha='a'*40, output=root/'output')
            if diagnostic:
                args.datasets = ['fixture']
            def native(command, stdout, stderr, **kwargs):
                block = int(command[command.index('--block')+1])
                bits = int(command[command.index('--sample-bits')+1])
                stable = command[command.index('--stable-note-identity')+1] == '1'
                trace = Path(command[command.index('--events')+1])
                trace.write_text(HEADER + '0\ton\t60\t0.75\t-1060\t0\n80\toff\t60\t0\t-1060\t0\n')
                data = dict(schema='m3_vst3_corpus_native_v1', routing='per_voice',
                    sample_bits=bits, block_samples=block, trial=True, sample_count=100, sample_rate=96000,
                    processed_samples=100, blocks=(100+block-1)//block, detector_samples=100,
                    detector_transitions=2, queue_rejections=0, event_add_attempts=2, accepted_events=2,
                    output_blocked_blocks=0, dry_audio_mismatches=0, process_failures=0,
                    output_blocked_at_eof=False, calibration_merge_matches=True, invalid_event=False,
                    trace_write_failed=False, first_blocked_sample=None, stable_note_identity=stable,
                    transferred_pairs=0, completion_midi_retention=False, process_measurement=None)
                if '--batch-cell-update' in command:
                    self.assertEqual(command[command.index('--batch-cell-update')+1], '1')
                    data['batch_cell_update'] = batch_fault != 'disabled'
                    if batch_fault == 'trace':
                        trace.write_text(trace.read_text().replace('0.75', '0.50'))
                    elif batch_fault == 'state':
                        data['dry_audio_mismatches'] = 1
                if '--measure-process' in command:
                    data['process_measurement'] = dict(scope=SCOPE, clock='steady_clock',
                        cold_blocks_included=True, allocation_guard=True, blocks=data['blocks'],
                        p99_ns=100, max_ns=400000 if fail_timing else 200, deadline_overruns=int(fail_timing),
                        cpp_allocations=0, cpp_frees=0, c_allocations=0, c_frees=0)
                stdout.write(json.dumps(data))
                return SimpleNamespace(returncode=0)
            with patch.object(runner, 'DATASETS', datasets), patch.object(runner, 'verify_references', return_value=4), \
                    patch.object(runner.subprocess, 'check_output', return_value='a'*40+'\n'), \
                    patch.object(runner.subprocess, 'run', side_effect=native) as process:
                if invalid_second:
                    with self.assertRaisesRegex(ValueError, 'bad.tsv: row 2'):
                        runner.run(args)
                    process.assert_not_called()
                    report = json.loads((args.output/'report.json').read_text())
                    self.assertEqual(report['stage'], 'bad/annotation-preflight')
                    self.assertEqual(report['state'], 'error')
                    return
                if batch:
                    baseline = runner.run(args)
                    saved = runner.component_reference_from_report(baseline, 'd'*64)
                    if batch_fault == 'provenance':
                        saved['source']['input_bundle_sha256'] = 'e'*64
                    args.component_reference = root/'component.json'
                    args.component_reference.write_text(json.dumps(saved))
                    args.batch_cell_update = True
                    args.output = root/'batch-output'
                    if batch_fault:
                        message = 'provenance differs' if batch_fault == 'provenance' else 'saved component identity failed'
                        with self.assertRaisesRegex(ValueError, message):
                            runner.run(args)
                        self.assertEqual(process.call_count, 16 if batch_fault == 'provenance' else 17)
                        if batch_fault != 'provenance':
                            report = json.loads((args.output/'report.json').read_text())
                            self.assertEqual(report['state'], 'error')
                            self.assertFalse(report['datasets']['fixture']['runs']['per_voice-32-512-plain']['gate_pass'])
                        return
                result = runner.run(args)
            self.assertEqual(process.call_count, 32 if batch else 16)
            self.assertEqual(json.loads((args.output/'report.json').read_text()), result)
            self.assertFalse(result['promotion_accepted'])
            return result

    def test_full_matrix_aggregates_and_persists(self):
        self.assertTrue(self.exercise()['corpus_gate_pass'])

    def test_timing_failure_prevents_corpus_acceptance(self):
        self.assertFalse(self.exercise(fail_timing=True)['corpus_gate_pass'])

    def test_batch_matrix_preserves_saved_component_output(self):
        result = self.exercise(batch=True)
        self.assertTrue(result['corpus_gate_pass'])
        self.assertEqual(result['schema'], 'm3_vst3_batch_cell_corpus_v1')
        for row in result['datasets']['fixture']['runs'].values():
            for name in ('batch_execution_enabled', 'saved_component_callbacks_identical',
                         'saved_component_outcome_identical'):
                self.assertTrue(row['gates'][name])

    def test_batch_identity_does_not_override_a_deadline_failure(self):
        self.assertFalse(self.exercise(batch=True, fail_timing=True)['corpus_gate_pass'])

    def test_batch_stops_after_first_changed_callback_or_state(self):
        for fault in ('trace', 'state', 'disabled'):
            with self.subTest(fault=fault):
                self.exercise(batch=True, batch_fault=fault)

    def test_batch_reference_provenance_checked_before_processing(self):
        self.exercise(batch=True, batch_fault='provenance')

    def test_batch_switch_and_reference_are_required_together(self):
        for args in (SimpleNamespace(batch_cell_update=True),
                     SimpleNamespace(component_reference=Path('unused'))):
            with self.assertRaisesRegex(ValueError, 'requires the saved component reference'):
                runner.run(args)

    def test_reference_builder_requires_complete_identical_matrix(self):
        report = self.exercise()
        with patch.object(runner, 'DATASETS', {'fixture': {}}):
            reference = runner.component_reference_from_report(report, 'd'*64)
            self.assertEqual(set(reference['datasets']['fixture']['modes']), set(runner.MODES))
            runs = report['datasets']['fixture']['runs']
            saved = runs.pop('stable_note-64-32-timed')
            with self.assertRaisesRegex(ValueError, 'Incomplete saved component matrix'):
                runner.component_reference_from_report(report, 'd'*64)
            runs['stable_note-64-32-timed'] = saved
            saved['trace']['raw_sha256'] = 'f'*64
            with self.assertRaisesRegex(ValueError, 'outcomes differ'):
                runner.component_reference_from_report(report, 'd'*64)

    def test_committed_reference_has_all_saved_modes_and_input_identity(self):
        root = Path(__file__).resolve().parents[1]
        reference = json.loads((root/'docs/recovery/batch-cell-vst3-corpus-references-20261122.json').read_text())
        replay = json.loads((root/'docs/recovery/calibrated-midi-retention-corpus-references-20261115.json').read_text())
        runner.verify_component_reference(reference, {'source': reference['source']}, replay)
        self.assertEqual(reference['source']['run_id'], '44245557161')
        self.assertEqual(sum(len(row['modes']) for row in reference['datasets'].values()), 28)
        reference['datasets']['ordinary']['clock']['sample_count'] += 1
        with self.assertRaisesRegex(ValueError, 'clock or modes differ'):
            runner.verify_component_reference(reference, {'source': reference['source']}, replay)

    def test_diagnostic_never_claims_corpus_acceptance(self):
        result = self.exercise(diagnostic=True)
        self.assertTrue(result['screen_gate_pass'])
        self.assertIsNone(result['corpus_gate_pass'])
        self.assertEqual(result['scope'], 'bounded diagnostic')
        self.assertFalse(self.exercise(diagnostic=True, fail_timing=True)['screen_gate_pass'])

    def test_invalid_selection_rejected_before_processing(self):
        for names in ([], ['unknown'], ['fixture', 'fixture']):
            with patch.object(runner, 'DATASETS', {'fixture': {}}):
                with self.assertRaisesRegex(ValueError, 'Dataset selection'):
                    runner.run(SimpleNamespace(datasets=names))

    def test_labels_cannot_exceed_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'labels.tsv'
            path.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n0\t101\t60\t1\n')
            with self.assertRaises(ValueError):
                runner.read_labels(path, 100)

    def test_all_annotations_checked_before_native_processing(self):
        self.exercise(invalid_second=True)

    def test_unknown_string_pitch_label_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'labels.tsv'
            path.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n0\t80\t48\t0\n')
            self.assertEqual(runner.read_labels(path, 100), [dict(
                label_index=0, start_sample=0, end_sample=80, midi_note=48, string_mask=0)])
            for mask in (-1, 256):
                path.write_text(f'start_sample\tend_sample\tmidi_note\tstring_mask\n0\t80\t48\t{mask}\n')
                with self.assertRaisesRegex(ValueError, 'row 2'):
                    runner.read_labels(path, 100)
