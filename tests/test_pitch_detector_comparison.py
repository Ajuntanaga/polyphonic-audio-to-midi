"""Synthetic note intervals only: no model import, audio I/O or native replay."""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.test_midi_lifecycle_analysis import event, label, trace
from tools import portable_basic_pitch_comparison as runner
from tools.pitch_detector_comparison import compare, digest, model_spans, native_spans, score, union_events


CLOCK = dict(sample_count=200, sample_rate=1000)


class ComparisonTests(unittest.TestCase):
    def test_rounding_clipping_and_full_model_pitch_range(self):
        spans, audit = model_spans([
            (-.01, .0205, 21, .5, None), (.1994, .3, 108, .7, []),
            (.3, .4, 60, .5, None), (.05, .0501, 60, .5, None)], **CLOCK)
        self.assertEqual(spans, [(0, 21, 21), (199, 200, 108)])
        self.assertEqual(audit, dict(raw_note_events=4, clipped_notes=3,
                                    empty_after_rounding_or_clipping=2))

    def test_malformed_predictions_cannot_be_scored_as_silence(self):
        for row in [(0, 1, 60, float('nan')), (0, float('inf'), 60, .5),
                    (.1, .1, 60, .5), (0, .1, 60.5, .5), (0, .1, 128, .5)]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                model_spans([row], **CLOCK)
        with self.assertRaises(ValueError):
            union_events([(0, 201, 60)], sample_count=200)

    def test_invalid_native_pairing_is_rejected_before_union(self):
        with self.assertRaisesRegex(ValueError, 'pairing'):
            native_spans([event(10, 'on'), event(20, 'on')], **CLOCK)
        spans, audit = native_spans([event(10, 'on')], **CLOCK)
        self.assertEqual(spans, [(10, 200, 60)])
        self.assertEqual(len(audit['open_at_recording_end']), 1)

    def test_lane_switches_and_duplicate_pitch_have_equal_occupancy(self):
        events = [event(20, 'on', voice=0), event(50, 'on', voice=1),
                  event(70, 'off', voice=0), event(90, 'off', voice=1),
                  event(90, 'on', voice=2), event(120, 'off', voice=2)]
        spans, audit = native_spans(events, **CLOCK)
        labels = [label(0, 20, 120, mask=1), label(1, 20, 120, mask=4)]
        native = score(spans, labels, **CLOCK)
        model = score([(20, 120, 60)], labels, **CLOCK)
        self.assertEqual(native, model)
        self.assertEqual(audit['raw_note_ons'], 3)
        self.assertEqual(model['pitch_sets']['totals']['expected_pitch_samples'], 100)
        self.assertEqual(set(model['pitch_sets']['by_distinct_pitch_count']), {'1'})

    def test_chord_presence_extras_and_gap_are_separate(self):
        labels = [label(0, 20, 120), label(1, 20, 120, note=64)]
        measured = score([(20, 120, 60), (50, 100, 64), (90, 150, 72)], labels, **CLOCK)
        totals = measured['pitch_sets']['totals']
        self.assertEqual(totals['expected_pitch_samples'], 200)
        self.assertEqual(totals['present_pitch_samples'], 150)
        self.assertEqual(totals['all_expected_pitches_samples'], 50)
        self.assertEqual(totals['exact_pitch_set_samples'], 40)
        self.assertEqual(totals['extra_pitch_voice_samples'], 30)
        self.assertEqual(measured['pitch_sets']['unlabeled_gap_voice_samples'], 30)

    def test_total_gain_cannot_hide_one_lost_label_or_shorter_hold(self):
        labels = [label(0, 20, 120), label(1, 20, 120, note=64)]
        current = score([(20, 120, 60)], labels, **CLOCK)
        for spans in [[(20, 119, 60), (20, 120, 64)],
                      [(20, 70, 60), (71, 120, 60), (20, 120, 64)]]:
            result = compare(current, score(spans, labels, **CLOCK))
            self.assertGreater(result['pitch_coverage_gain_pp'], 0)
            self.assertFalse(result['no_pitch_safety_regression'])

    def test_hold_alignment_loss_cannot_hide_behind_equal_label_totals(self):
        labels = [label(0, 20, 120), label(1, 20, 120, note=64)]
        current = score([(20, 70, 60), (20, 70, 64)], labels, **CLOCK)
        model = score([(20, 70, 60), (70, 120, 64)], labels, **CLOCK)
        result = compare(current, model)
        self.assertEqual(result['label_changes'], [])
        self.assertEqual(len(result['label_deltas']), 2)
        for row in result['label_deltas']:
            self.assertEqual(row['present_samples_delta'], 0)
            self.assertEqual(row['longest_present_samples_delta'], 0)
        self.assertEqual(result['pitch_coverage_gain_pp'], 0)
        self.assertFalse(result['no_pitch_safety_regression'])

    def test_false_pitch_or_gap_growth_rejects_even_full_recall(self):
        labels = [label(0, 20, 120), label(1, 20, 120, note=64)]
        current = score([(20, 120, 60)], labels, **CLOCK)
        for extra in [(30, 40, 72), (120, 130, 64)]:
            result = compare(current, score([(20, 120, 60), (20, 120, 64), extra], labels, **CLOCK))
            self.assertEqual(result['model_pitch_coverage_percent'], 100)
            self.assertFalse(result['no_pitch_safety_regression'])

    def test_clock_or_label_mismatch_fails(self):
        current = score([], [label()], **CLOCK)
        for field in ['sample_rate', 'sample_count']:
            candidate = copy.deepcopy(current)
            candidate[field] += 1
            with self.assertRaises(ValueError):
                compare(current, candidate)
        candidate = copy.deepcopy(current)
        candidate['labels'][0]['midi_note'] += 1
        with self.assertRaises(ValueError):
            compare(current, candidate)


class RunnerTests(unittest.TestCase):
    def test_cli_remote_guard_precedes_all_io(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'must-not-exist'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_basic_pitch_comparison',
                '--spec', 'absent', '--inputs', 'absent', '--model-checkout', 'absent',
                '--output', str(out)], env={k:v for k,v in os.environ.items() if k != 'GITHUB_ACTIONS'},
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertNotIn('TypeError', result.stderr)
            self.assertFalse(out.exists())

    def test_synthetic_prediction_then_labels_once(self):
        calls = []
        settings = dict(onset_threshold=.5, frame_threshold=.3)

        class FakeBackend:
            def audio_info(self, path):
                calls.append('clock')
                return dict(**CLOCK, channels=1, subtype='SYNTHETIC')

            def predict(self, path, passed):
                calls.append('predict')
                self_test.assertEqual(passed, settings)
                return {}, [(.02, .12, 60, .7, None), (.02, .12, 64, .4, [0])]

            def save_arrays(self, path, arrays):
                calls.append('save_arrays')
                path.write_bytes(b'synthetic placeholder; no model or audio')
                return {}

        def annotations(path):
            self.assertEqual(calls, ['clock', 'predict', 'save_arrays'])
            calls.append('labels')
            return labels

        self_test = self
        labels = [label(0, 20, 120), label(1, 20, 120, note=64)]
        baseline = dict(run_id=123, pitch_spans=[(20, 120, 60)],
                        measurement=score([(20, 120, 60)], labels, **CLOCK))
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GITHUB_ACTIONS':'true'}):
            root = Path(directory)
            with patch.object(runner, 'read_labels', side_effect=annotations):
                result = runner.measure_dataset('ordinary', CLOCK, baseline, root, root, settings, FakeBackend())
            self.assertEqual(result['comparison']['pitch_coverage_gain_pp'], 50)
            self.assertTrue(result['comparison']['no_pitch_safety_regression'])
            self.assertEqual(calls.count('predict'), 1)
            self.assertEqual(len(json.loads((root / 'ordinary-notes.json').read_text())['events']), 2)
            self.assertEqual(result['bulk']['ordinary-notes.json']['sha256'], digest(root / 'ordinary-notes.json'))

    def test_negative_control_and_gain_both_required_and_never_promotion(self):
        rows = {name:dict(comparison=dict(pitch_coverage_gain_pp=5., no_pitch_safety_regression=True))
                for name in ('ordinary', 'extended-middle')}
        self.assertTrue(runner.research_screen(rows)['research_screen_pass'])
        self.assertFalse(runner.research_screen(rows)['promotion_accepted'])
        rows['extended-middle']['comparison']['no_pitch_safety_regression'] = False
        self.assertFalse(runner.research_screen(rows)['research_screen_pass'])
        rows['extended-middle']['comparison']['no_pitch_safety_regression'] = True
        rows['ordinary']['comparison']['pitch_coverage_gain_pp'] = 4.99
        self.assertFalse(runner.research_screen(rows)['research_screen_pass'])
        with self.assertRaises(ValueError):
            runner.research_screen({'ordinary':rows['ordinary']})

    def test_bad_model_pin_fails_before_model_or_audio_access_and_saves_failure(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                {'GITHUB_ACTIONS':'true', 'GITHUB_REPOSITORY':'fixture/worker', 'SOURCE_SHA':'a'*40}):
            root = Path(directory)
            spec = root / 'spec.json'
            spec.write_text(json.dumps(dict(worker_repository='fixture/worker', model=dict(commit='b'*40))))
            with patch.object(runner, 'captured_text', side_effect=['a'*40, 'c'*40]), \
                    patch.object(runner, 'OnnxBackend') as backend:
                with self.assertRaisesRegex(ValueError, 'revision mismatch'):
                    runner.run(spec, root, root, root / 'output')
                backend.assert_not_called()
            result = json.loads((root / 'output/report/report.json').read_text())
            self.assertEqual(result['state'], 'failed')
            self.assertEqual(result['datasets'], {})

    def test_full_synthetic_run_scores_both_once_even_when_first_fails_quality(self):
        predicted = []

        class FakeBackend:
            metadata = dict(providers=['SYNTHETIC'])

            def __init__(self, model_path):
                pass

            def audio_info(self, path):
                return dict(**CLOCK, channels=1, subtype='SYNTHETIC')

            def predict(self, path, settings):
                predicted.append(path.stem)
                notes = [(.02, .12, 60, .7, None)]
                if path.stem == 'ordinary':
                    # Complementary detector loses most of CURRENT's note 60,
                    # gains note 64, and adds a false note in an unlabeled gap.
                    notes = [(.02, .03, 60, .7, None), (.02, .12, 64, .4, None),
                             (.13, .14, 72, .5, None)]
                return {}, notes

            def save_arrays(self, path, arrays):
                path.write_bytes(b'synthetic arrays; no model or audio')
                return {}

        env = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY='fixture/worker',
                   SOURCE_SHA='a'*40, GITHUB_SHA='d'*40, GITHUB_RUN_ID='123',
                   GITHUB_RUN_ATTEMPT='1', INPUT_SHA256='e'*64)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env):
            root = Path(directory)
            corpus = root / 'corpus'
            corpus.mkdir()
            model = root / 'model.onnx'
            model.write_bytes(b'synthetic model placeholder')
            manifest = root / 'recovery-inputs.json'
            manifest.write_text('{}')
            configs, baselines = {}, {}
            for name in ('ordinary', 'extended-middle'):
                wav, annotation = corpus / (name + '.wav'), corpus / (name + '.tsv')
                wav.write_bytes(b'synthetic placeholder, never decoded')
                annotation.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n'
                                      '20\t120\t60\t1\n' +
                                      ('20\t120\t64\t2\n' if name == 'ordinary' else ''))
                provenance = dict(run_id=100, source_commit='a'*40, raw_midi_sha256='f'*64)
                configs[name] = dict(**CLOCK, wav_sha256=digest(wav),
                                     labels_sha256=digest(annotation), baseline=provenance)
                baselines[name] = dict(**provenance, labels_sha256=digest(annotation),
                    pitch_spans=[(20, 120, 60)],
                    measurement=score([(20, 120, 60)], runner.read_labels(annotation), **CLOCK))
            baseline = root / 'baseline.json'
            baseline.write_text(json.dumps(dict(datasets=baselines)))
            spec = root / 'spec.json'
            spec.write_text(json.dumps(dict(worker_repository='fixture/worker',
                model=dict(commit='b'*40, path='model.onnx', sha256=digest(model)),
                baseline_file=str(baseline), baseline_sha256=digest(baseline),
                input_manifest_sha256=digest(manifest), input_bundle_sha256='e'*64,
                input_release='synthetic', datasets=configs, prediction={}, protocol={})))
            with patch.object(runner, 'captured_text', side_effect=['a'*40, 'b'*40, 'synthetic==1']), \
                    patch.object(runner, 'OnnxBackend', FakeBackend):
                result = runner.run(spec, root, root, root / 'output')
            self.assertEqual(predicted, ['ordinary', 'extended-middle'])
            self.assertEqual(result['state'], 'completed')
            self.assertTrue(result['final'])
            self.assertFalse(result['screen']['research_screen_pass'])
            self.assertTrue(result['screen']['useful_pitch_gain'])
            self.assertFalse(result['screen']['promotion_accepted'])
            ordinary = result['datasets']['ordinary']
            delta = ordinary['comparison']['label_deltas'][0]
            self.assertEqual(delta['present_samples_delta'], -90)
            self.assertEqual(delta['longest_present_samples_delta'], -90)
            union = ordinary['report_only_union']
            self.assertTrue(union['report_only'])
            self.assertFalse(union['affects_research_screen'])
            self.assertFalse(union['promotion_accepted'])
            self.assertEqual(union['comparison_to_saved_current']['model_pitch_coverage_percent'], 100)
            self.assertEqual(union['added_present_pitch_samples_over_saved_current'], 100)
            self.assertEqual(union['added_present_pitch_samples_over_basic_pitch'], 90)
            self.assertEqual(union['measurement']['pitch_sets']['unlabeled_gap_voice_samples'], 10)
            self.assertFalse(union['comparison_to_saved_current']['no_pitch_safety_regression'])
            self.assertEqual(len(result['datasets']['extended-middle']['comparison']['label_deltas']), 1)
            # Union diagnostics cannot rescue or veto the frozen direct screen.
            verdict = runner.research_screen(result['datasets'])
            union['comparison_to_saved_current']['no_pitch_safety_regression'] = True
            self.assertEqual(runner.research_screen(result['datasets']), verdict)
            union['comparison_to_saved_current']['no_pitch_safety_regression'] = False
            self.assertEqual(result['provenance']['worker_commit'], 'd'*40)
            saved = json.loads((root / 'output/report/report.json').read_text())
            self.assertEqual(saved, result)
            self.assertEqual(len(list((root / 'output/bulk').iterdir())), 4)

    def test_exporter_cli_uses_saved_text_only_and_refuses_reference_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            midi, labels = root / 'midi.tsv', root / 'labels.tsv'
            trace(midi, [event(20, 'on', sequence=0), event(120, 'off', sequence=1)])
            labels.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n20\t120\t60\t1\n')
            zipped = root / 'midi.tsv.gz'
            zipped.write_bytes(gzip.compress(midi.read_bytes()))
            spec = root / 'spec.json'
            spec.write_text(json.dumps(dict(datasets=dict(ordinary=dict(**CLOCK, labels_sha256=digest(labels),
                baseline=dict(local_labels=str(labels), local_midi_gzip=str(zipped), raw_midi_sha256=digest(midi),
                              transitions=2, run_id=123, source_commit='a'*40))))))
            out = root / 'reference.json'
            command = [sys.executable, '-m', 'tools.prepare_pitch_comparison_baseline',
                       '--spec', str(spec), '--output', str(out)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            reference = json.loads(out.read_text())['datasets']['ordinary']
            self.assertEqual(reference['pitch_spans'], [[20, 120, 60]])
            self.assertEqual(reference['measurement']['labels'][0]['present_samples'], 100)
            before = hashlib.sha256(out.read_bytes()).hexdigest()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn('FileExistsError', second.stderr)
            self.assertEqual(digest(out), before)


if __name__ == '__main__':
    unittest.main()
