"""Pure synthetic contracts; no recording, model, native replay or download."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from tests.test_midi_lifecycle_analysis import label
from tools import portable_fretnet_comparison as runner
from tools.fretnet_comparison import (decode_tablature, evaluate, frame_windows,
    label_budget, research_screen, tablature_spans)
from tools.pitch_detector_comparison import compare, digest, score


CLOCK = dict(sample_count=200, sample_rate=1000)
ENV = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY='fixture/worker',
    SOURCE_SHA='a'*40, GITHUB_SHA='d'*40, GITHUB_RUN_ID='123',
    GITHUB_RUN_ATTEMPT='1', INPUT_SHA256='e'*64)


def sigmoid(value):
    return 1 / (1 + np.exp(-np.clip(value, -80, 80)))


def logits(frames, positions):
    result = np.full((1, frames, 6, 21), -8, dtype=np.float32)
    for string, fret in enumerate(positions):
        result[0, :, string, fret + 1] = 8
    return result.reshape(1, frames, 126)


class AdapterTests(unittest.TestCase):
    def test_windows_have_centered_context_and_zero_edges(self):
        values = np.broadcast_to(np.arange(1, 4, dtype=np.float32), (6, 144, 3))
        framed = frame_windows(values)
        self.assertEqual(framed.shape, (1, 3, 6, 144, 9))
        self.assertTrue(framed.flags.c_contiguous)
        np.testing.assert_array_equal(framed[0, 0, 0, 0], [0, 0, 0, 0, 1, 2, 3, 0, 0])
        np.testing.assert_array_equal(framed[0, 2, 0, 0], [0, 0, 1, 2, 3, 0, 0, 0, 0])

    def test_bad_features_and_logits_fail_instead_of_becoming_silence(self):
        for array in (np.zeros((6, 144, 0)), np.zeros((5, 144, 1)), np.full((6, 144, 1), np.nan)):
            with self.assertRaises(ValueError):
                frame_windows(array)
        for array in (np.zeros((1, 2, 126)), np.zeros((1, 2, 120), dtype=np.float32),
                      np.full((1, 2, 126), np.inf, dtype=np.float32)):
            with self.assertRaises(ValueError):
                decode_tablature(array, sigmoid)

    def test_silence_first_and_upper_fret_profile(self):
        decoded = decode_tablature(logits(2, [-1, 0, 19, 1, 2, 3]), sigmoid)
        np.testing.assert_array_equal(decoded[:, 0], [-1, 0, 19, 1, 2, 3])

    def test_sigmoid_precedes_argmax_including_saturation_tie(self):
        raw = logits(1, [-1]*6).reshape(1, 1, 6, 21)
        raw[0, 0, 0] = -80
        raw[0, 0, 0, 1:3] = [90, 100]
        self.assertEqual(decode_tablature(raw.reshape(1, 1, 126), sigmoid)[0, 0], 0)
        self.assertEqual(raw[0, 0, 0].argmax() - 1, 1)

    def test_all_negative_logits_still_use_author_argmax_not_threshold(self):
        raw = np.full((1, 1, 6, 21), -8, dtype=np.float32)
        raw[0, 0, :, 5] = -2
        np.testing.assert_array_equal(decode_tablature(raw.reshape(1, 1, 126), sigmoid),
                                      np.full((6, 1), 4))

    def test_nominal_clock_same_pitch_union_and_eof_clip(self):
        frets = np.full((6, 3), -1, dtype=np.int64)
        frets[0, :2] = 5  # MIDI 45, then the second string carries it.
        frets[1, 1:] = 0
        frets[5, 2] = 19
        self.assertEqual(tablature_spans(frets, sample_count=60, sample_rate=1000),
                         [(0, 60, 45), (46, 60, 83)])
        frets[:, :] = -1
        self.assertEqual(tablature_spans(frets, sample_count=60, sample_rate=1000), [])

    def test_short_horizon_and_nonsemantic_tablature_are_rejected(self):
        for frets in (np.zeros((6, 1), dtype=np.int64), np.full((6, 10), 20),
                      np.zeros((6, 10), dtype=np.float32)):
            with self.assertRaises(ValueError):
                tablature_spans(frets, **CLOCK)

    def test_budget_enforces_both_limits_and_no_new_miss(self):
        def changed(length, loss):
            labels = [label(0, 0, length), label(1, 0, length, note=64)]
            clock = dict(sample_count=2000, sample_rate=1000)
            before = score([(0, length, 60)], labels, **clock)
            after = score([(loss, length, 60)] if loss < length else [], labels, **clock)
            return label_budget(compare(before, after), 1000)
        self.assertTrue(changed(1000, 25)['budget_screen_pass'])
        self.assertFalse(changed(1000, 25)['strict_screen_pass'])
        self.assertEqual(changed(1000, 26)['failed_labels'], 1)
        self.assertTrue(changed(200, 10)['budget_screen_pass'])
        self.assertEqual(changed(200, 11)['failed_labels'], 1)
        self.assertIn('newly_entirely_missed', changed(1, 1)['failures'][0]['reasons'])

    def test_longest_hold_and_false_gap_are_not_hidden_by_total_gain(self):
        labels = [label(0, 20, 120), label(1, 20, 120, note=64)]
        old = score([(20, 120, 60)], labels, **CLOCK)
        new = score([(20, 70, 60), (71, 120, 60), (20, 120, 64)], labels, **CLOCK)
        budget = label_budget(compare(old, new), 1000)
        self.assertEqual(budget['failures'][0]['reasons'], ['longest_present'])
        new = score([(20, 120, 60), (20, 120, 64), (140, 150, 72)], labels, **CLOCK)
        self.assertFalse(label_budget(compare(old, new), 1000)['aggregate_safe'])

    def test_out_of_range_labels_retained_and_union_is_report_only(self):
        labels = [label(0, 20, 120, note=32), label(1, 20, 120, note=64)]
        spans = [(20, 120, 32)]
        baseline = dict(pitch_spans=spans, measurement=score(spans, labels, **CLOCK))
        result = evaluate([(20, 120, 64)], labels, baseline, **CLOCK)
        self.assertEqual(result['unsupported_range']['label_indices'], [0])
        self.assertEqual(result['arms']['fretnet']['comparison']['model_pitch_coverage_percent'], 50)
        self.assertEqual(result['arms']['union']['comparison']['model_pitch_coverage_percent'], 100)
        self.assertTrue(result['arms']['union']['report_only'])
        # The split preserves CURRENT's low pitch and retains model upper pitches.
        self.assertEqual(result['arms']['pitch_split_60']['comparison']['model_pitch_coverage_percent'], 100)
        baseline['measurement']['sample_count'] = 201
        with self.assertRaisesRegex(ValueError, 'does not reproduce'):
            evaluate([], labels, baseline, **CLOCK)

    def test_both_corpora_and_useful_gain_required_never_promotion(self):
        row = dict(comparison=dict(pitch_coverage_gain_pp=5.),
                   label_budget=dict(strict_screen_pass=True, budget_screen_pass=True))
        datasets = {n:dict(arms={a:copy.deepcopy(row) for a in ('fretnet','union','pitch_split_60')})
                    for n in ('ordinary','extended-middle')}
        self.assertTrue(research_screen(datasets)['arms']['fretnet']['budget_pass'])
        datasets['extended-middle']['arms']['fretnet']['label_budget']['budget_screen_pass'] = False
        self.assertFalse(research_screen(datasets)['arms']['fretnet']['budget_pass'])
        datasets['ordinary']['arms']['union']['comparison']['pitch_coverage_gain_pp'] = 4.99
        self.assertFalse(research_screen(datasets)['arms']['union']['budget_pass'])
        self.assertFalse(research_screen(datasets)['promotion_accepted'])
        with self.assertRaises(ValueError):
            research_screen({'ordinary':datasets['ordinary']})


class RunnerTests(unittest.TestCase):
    def test_remote_guard_precedes_optional_imports_and_file_access(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_fretnet_comparison',
                '--spec','absent','--inputs','absent','--output',str(out)],
                env={k:v for k,v in os.environ.items() if k != 'GITHUB_ACTIONS'},
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(out.exists())

    def test_download_pin_checked_and_no_retry(self):
        payload = b'synthetic model placeholder, never executed'
        blob = hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
        asset = dict(name='m.onnx', path='known/m.onnx', bytes=len(payload), git_blob_sha1=blob)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, ENV):
            with patch.object(runner.urllib.request, 'urlopen', return_value=io.BytesIO(payload)) as fetch:
                path, receipt = runner.download_pinned(asset, Path(directory), 'fixture/model', 'a'*40)
                self.assertEqual(receipt['sha256'], digest(path))
                with self.assertRaisesRegex(ValueError, 'does not retry'):
                    runner.download_pinned(asset, Path(directory), 'fixture/model', 'a'*40)
                self.assertEqual(fetch.call_count, 1)
            asset['name'] = 'wrong.onnx'
            with patch.object(runner.urllib.request, 'urlopen', return_value=io.BytesIO(payload+b'!')):
                with self.assertRaisesRegex(ValueError, 'differs'):
                    runner.download_pinned(asset, Path(directory), 'fixture/model', 'a'*40)

    def test_hcqt_expected_frame_private_helper_is_not_name_mangled(self):
        calls = []
        def early(**kwargs):
            calls.append(kwargs)
            return 0
        fake = SimpleNamespace(core=SimpleNamespace(constantq=SimpleNamespace(
            **{'__early_downsample_count':early})), note_to_hz=lambda value:82.4,
            cqt_frequencies=lambda **kwargs:[1000], filters=SimpleNamespace(window_bandwidth=lambda w:1.5),
            vqt=lambda audio, **kwargs:np.ones((144, 3), dtype=np.float32),
            amplitude_to_db=lambda value, **kwargs:np.zeros_like(value))
        backend = object.__new__(runner.Backend)
        backend.np, backend.librosa = np, fake
        values, times = backend.hcqt(np.zeros(1024, dtype=np.float32))
        self.assertEqual(values.shape, (6, 144, 3))
        self.assertEqual(len(calls), 6)
        np.testing.assert_allclose(times, np.arange(3)*512/22050)

    def test_reference_outputs_and_frontend_are_fail_closed(self):
        hcqt = np.arange(6*144*3, dtype=np.float32).reshape(6,144,3)/10000
        raw = dict(tablature=logits(3, [-1]*6),
            tablature_rel=np.zeros((1,3,120), dtype=np.float32), onsets=np.zeros((1,3,120), dtype=np.float32))
        backend = SimpleNamespace(np=np, sigmoid=sigmoid,
            infer=lambda features, chunk=128:raw,
            hcqt=lambda audio:(hcqt, np.arange(3)*512/22050))
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, ENV):
            paths = {n:Path(directory)/(n+'.npz') for n in ('front','forward')}
            np.savez(paths['front'], audio=np.ones(1024, dtype=np.float32), hcqt=hcqt)
            np.savez(paths['forward'], features=frame_windows(hcqt), times=np.arange(3)*512/22050, **raw)
            pairs = [dict(name='synthetic', frontend='front', forward='forward')]
            self.assertTrue(runner.reference_checks(backend, paths, pairs)['synthetic']['passed'])
            bad = copy.deepcopy(raw)
            bad['tablature'][0,0,1] = 20
            backend.infer = lambda features, chunk=128:bad
            self.assertFalse(runner.reference_checks(backend, paths, pairs)['synthetic']['passed'])

    def run_fixture(self, directory, reference_pass=True, bad_input=False):
        root = Path(directory)
        corpus = root/'corpus'
        corpus.mkdir()
        (root/'recovery-inputs.json').write_text('{}')
        configs, baselines = {}, {}
        for name in ('ordinary','extended-middle'):
            wav, annotation = corpus/(name+'.wav'), corpus/(name+'.tsv')
            wav.write_bytes(b'placeholder, not decoded')
            annotation.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n20\t120\t60\t1\n')
            provenance = dict(run_id=1, source_commit='a'*40, raw_midi_sha256='b'*64)
            configs[name] = dict(**CLOCK, wav_sha256=digest(wav), labels_sha256=digest(annotation), baseline=provenance)
            baselines[name] = dict(**provenance, labels_sha256=digest(annotation), pitch_spans=[(20,120,60)],
                measurement=score([(20,120,60)], [label(0,20,120)], **CLOCK))
        baseline_path = root/'baseline.json'
        baseline_path.write_text(json.dumps(dict(datasets=baselines)))
        spec = dict(worker_repository='fixture/worker', input_bundle_sha256='e'*64,
            input_manifest_sha256=digest(root/'recovery-inputs.json'), baseline_file=str(baseline_path),
            baseline_sha256=digest(baseline_path), datasets=configs, model=dict(repository='fixture/model',commit='c'*40),
            protocol={}, assets=[dict(name='model.onnx')], reference_pairs=[])
        if bad_input:
            configs['ordinary']['wav_sha256'] = '0'*64
        spec_path = root/'spec.json'
        spec_path.write_text(json.dumps(spec))
        calls = []
        class FakeBackend:
            np = np
            metadata = dict(providers=['SYNTHETIC'])
            sf = SimpleNamespace(info=lambda path:SimpleNamespace(frames=200,samplerate=1000,channels=1))
            sigmoid = staticmethod(sigmoid)
            def __init__(self, path):
                calls.append('backend')
            def load_audio(self, path):
                calls.append(path.stem)
                return np.zeros(1, dtype=np.float32)
            def hcqt(self, audio):
                return np.zeros((6,144,9), dtype=np.float32), np.arange(9)*512/22050
            def infer(self, features):
                return dict(tablature=logits(9, [-1]*6))
        def annotation(path):
            self.assertTrue((root/'output/bulk'/(path.stem+'-outputs.npz')).exists())
            return [label(0,20,120)]
        with patch.dict(os.environ, ENV), patch.object(runner, 'captured_text', return_value='a'*40), \
                patch.object(runner, 'download_pinned', return_value=(root/'model.onnx',{})) as download, \
                patch.object(runner, 'Backend', FakeBackend), \
                patch.object(runner, 'read_labels', side_effect=annotation), \
                patch.object(runner, 'reference_checks', return_value={'synthetic':dict(passed=reference_pass)}):
            if not reference_pass or bad_input:
                with self.assertRaises(ValueError):
                    runner.run(spec_path, root, root/'output')
            else:
                runner.run(spec_path, root, root/'output')
            download_count = download.call_count
        report = json.loads((root/'output/report/report.json').read_text())
        return report, calls, download_count

    def test_reference_failure_stops_before_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            result, calls, downloads = self.run_fixture(directory, reference_pass=False)
            self.assertEqual(result['state'], 'failed')
            self.assertEqual(result['datasets'], {})
            self.assertEqual(calls, ['backend'])

    def test_wrong_input_hash_stops_before_any_download_or_model(self):
        with tempfile.TemporaryDirectory() as directory:
            result, calls, downloads = self.run_fixture(directory, bad_input=True)
            self.assertEqual(result['state'], 'failed')
            self.assertEqual(calls, [])
            self.assertEqual(downloads, 0)

    def test_both_recordings_scored_once_even_when_first_quality_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            result, calls, downloads = self.run_fixture(directory)
            self.assertEqual(calls, ['backend','ordinary','extended-middle'])
            self.assertEqual(set(result['datasets']), {'ordinary','extended-middle'})
            self.assertEqual(result['verdict'], 'REJECTED_OFFLINE_PITCH_SCREEN')
            self.assertTrue(result['final'])
            self.assertFalse(result['screen']['promotion_accepted'])


if __name__ == '__main__':
    unittest.main()
