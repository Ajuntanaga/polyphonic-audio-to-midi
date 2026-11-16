import copy
from contextlib import ExitStack
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from tests.test_candidate_outcome_analysis import candidate
from tools.candidate_outcome_analysis import HEADER, _frame
from tools.portable_assignment_trace import digest
from tools.portable_ordinary_harmonic_prediction import (
    CASES, CONFIG, END, RATE, SAMPLES, base_pitches, harmonic_frequencies,
    observations, prediction, read_outcomes, read_retained_outcomes, run, summarize)


MODULE = 'tools.portable_ordinary_harmonic_prediction.'
REFERENCE = Path(__file__).resolve().parents[1] / 'docs/recovery/ordinary-harmonic-prediction-references-20261116.json'


def state(sample=3839, text=None):
    text = candidate(47, selection=4) if text is None else text
    return _frame(f'{sample}\t{(sample + 1) // 64}\t0\t{sample + 1}\t\t\t\t{text}\n')


def prefix_bytes():
    lines = ['# m3_candidate_outcome_v2\n', HEADER]
    for index in range(END // 64):
        sample = 63 + 64 * index
        case = next((c for c in CASES if c['start_sample'] <= sample < c['end_sample']), None)
        labels = ','.join(f'{i}:60:1' for i in case['expected_labels']) if case else ''
        text = candidate(case['candidate_note'], selection=1) if case else ''
        lines.append(f'{sample}\t{index + 1}\t0\t{sample + 1}\t{labels}\t\t\t{text}\n')
    return ''.join(lines).encode()


class OrdinaryHarmonicPredictionTests(unittest.TestCase):
    def test_baseline_uses_owned_pitches_and_valid_causal_phase_not_labels(self):
        frame = state(text=','.join((candidate(47, selection=4, phase_valid=1, phase_cents=12),
            candidate(58, active=1, phase_cents=80), candidate(75, selection=1))))
        frame['labels'] = [(10, 75, 128)]
        pitches = base_pitches(frame)
        self.assertEqual([p['note'] for p in pitches], [47, 58])
        self.assertEqual([p['phase_cents'] for p in pitches], [12, 0])
        self.assertAlmostEqual(pitches[0]['frequency_hz'], 440 * 2 ** ((47 - 69 + .12) / 12))
        frequencies = harmonic_frequencies(pitches)
        self.assertTrue(any(abs(f - pitches[0]['frequency_hz'] * 10) < 1e-8 for f in frequencies))
        self.assertTrue(all(f <= 3000 for f in frequencies))

    def test_parent_upper_harmonics_do_not_create_a_missing_note_gain(self):
        time = np.arange(4800) / RATE
        parent = 440 * 2 ** ((47 - 69) / 12)
        signal = np.cos(2 * np.pi * parent * time) + .4 * np.sin(2 * np.pi * parent * 10 * time)
        result = prediction(signal, 4799, state(), 75)
        self.assertEqual(result['status'], 'measured')
        self.assertLess(result['base_prediction_error_fraction'], 1e-20)
        self.assertLess(abs(result['prediction_gain_fraction']), 1e-20)
        self.assertGreater(result['base_partials'], 6)

    def test_independent_missing_pitch_predicts_held_out_audio(self):
        time = np.arange(4800) / RATE
        parent, missing = [440 * 2 ** ((note - 69) / 12) for note in (47, 75)]
        signal = np.cos(2 * np.pi * parent * time) + .4 * np.sin(2 * np.pi * missing * time)
        result = prediction(signal, 4799, state(), 75)
        self.assertGreater(result['prediction_gain_fraction'], .01)
        self.assertLess(result['added_prediction_error_fraction'], 1e-20)

    def test_shared_octave_columns_report_nonidentifiability(self):
        time = np.arange(4800) / RATE
        parent = 440 * 2 ** ((58 - 69) / 12)
        signal = np.sin(2 * np.pi * parent * time) + .3 * np.sin(2 * np.pi * parent * 2 * time)
        result = prediction(signal, 4799, state(text=candidate(58, selection=4)), 70)
        self.assertLess(result['candidate_independent_fraction_min'], 1e-20)
        self.assertLess(result['full_rank'], result['full_columns'])
        self.assertLess(abs(result['prediction_gain_fraction']), 1e-20)

    def test_future_audio_and_labels_cannot_change_prediction(self):
        signal = np.sin(2 * np.pi * 123.47 * np.arange(4900) / RATE)
        frame = state()
        before = prediction(signal, 4799, frame, 75)
        signal[4800:] = np.nan
        frame['labels'] = [(1, 70, 1)]
        self.assertEqual(prediction(signal, 4799, frame, 75), before)
        frame['sample'] = 3840
        with self.assertRaisesRegex(ValueError, 'prediction-period'):
            prediction(signal, 4799, frame, 75)
        with self.assertRaisesRegex(ValueError, 'shorter'):
            prediction(signal[:4799], 4799, state(), 75)

    def test_unavailable_measurements_are_not_zero_gain(self):
        for args, status in (((np.zeros(4800), 4799, state(), 75), 'zero_energy'),
            ((np.ones(4800), 1023, None, 75), 'insufficient_history'),
            ((np.ones(4800), 4799, state(text=''), 75), 'unavailable_base'),
            ((np.ones(4800), 4799, state(text=candidate(75, active=1)), 75), 'already_owned')):
            result = prediction(*args)
            self.assertEqual(result['status'], status)
            self.assertNotIn('prediction_gain_fraction', result)

    def test_retained_prefix_requires_exact_hashes_unique_member_and_complete_clock(self):
        raw = prefix_bytes()
        self.assertEqual(len(read_outcomes(raw)), END // 64)
        for bad in (raw.rsplit(b'\n', 2)[0] + b'\n', raw.replace(b'127\t2\t', b'128\t2\t', 1)):
            with self.assertRaises(ValueError):
                read_outcomes(bad)
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'saved.zip'
            packed = gzip.compress(raw)
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('prefix/outcome.tsv.gz', packed)
            spec = dict(bytes=archive.stat().st_size, sha256=digest(archive), member_suffix='outcome.tsv.gz',
                compressed_bytes=len(packed), compressed_sha256=hashlib.sha256(packed).hexdigest(),
                raw_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
            self.assertEqual(len(read_retained_outcomes(archive, dict(artifact=spec))[0]), END // 64)
            for key in ('bytes', 'sha256', 'compressed_bytes', 'compressed_sha256', 'raw_bytes', 'raw_sha256'):
                bad = dict(spec, **{key: 0 if key.endswith('bytes') else '0' * 64})
                with self.subTest(key=key), self.assertRaises(ValueError):
                    read_retained_outcomes(archive, dict(artifact=bad))
            with zipfile.ZipFile(archive, 'a') as bundle:
                bundle.writestr('other/outcome.tsv.gz', packed)
            spec.update(bytes=archive.stat().st_size, sha256=digest(archive))
            with self.assertRaisesRegex(ValueError, 'unique'):
                read_retained_outcomes(archive, dict(artifact=spec))

    def test_schedule_is_label_independent_and_summary_keeps_cross_boundary_history(self):
        frames = read_outcomes(prefix_bytes())
        calls = []
        def observe(audio, sample, frame, note):
            calls.append((sample, frame['sample'] if frame else None, note))
            return dict(available_sample=sample, candidate_note=note, status='unavailable_base',
                        window_start_sample=sample + 1 - 4800)
        with patch(MODULE + 'prediction', side_effect=observe):
            rows = observations(None, frames)
        expected = sorted(set(range(1023, END, 1024)) | {c['example_sample'] for c in CASES})
        self.assertEqual([r[0] for r in calls[::2]], expected)
        self.assertTrue(all(frame is None or frame <= sample - 960 for sample, frame, _ in calls))
        summaries = summarize(rows, frames)
        self.assertTrue(summaries[0]['example']['window_starts_before_case'])
        self.assertEqual(summaries[0]['groups']['all']['positive_prediction_gains'], 0)
        self.assertIsNone(summaries[0]['groups']['all']['prediction_gain_fraction']['p50'])
        frames[(CASES[0]['example_sample'] - 63) // 64]['labels'] = []
        with self.assertRaisesRegex(ValueError, 'annotation'):
            summarize(rows, frames)

    def test_runner_records_observation_completion_and_preserves_failure(self):
        reference = json.loads(REFERENCE.read_text())
        self.assertEqual(reference['config'], CONFIG)
        anchor_path = REFERENCE.parent / reference['anchor_file']
        self.assertEqual(digest(anchor_path), reference['anchor_sha256'])
        anchor = json.loads(anchor_path.read_text())
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                root = Path(directory)
                wav = root / 'ordinary.wav'
                wav.write_bytes(b'fixture')
                manifest = root / 'manifest.json'
                manifest.write_text(json.dumps(dict(source=anchor['source'], files=anchor['inputs'])))
                anchor['inputs']['ordinary.wav']['bytes'] = wav.stat().st_size
                anchor['inputs']['ordinary.wav']['sha256'] = digest(wav)
                (root / 'anchor.json').write_text(json.dumps(anchor))
                local = copy.deepcopy(reference)
                local.update(anchor_file='anchor.json', anchor_sha256=digest(root / 'anchor.json'))
                (root / 'reference.json').write_text(json.dumps(local))
                stack.enter_context(patch(MODULE + 'validate_reference'))
                stack.enter_context(patch(MODULE + 'read_retained_outcomes', return_value=([], {})))
                stack.enter_context(patch('scipy.io.wavfile.read', return_value=(RATE, np.zeros(SAMPLES, dtype=np.int16))))
                stack.enter_context(patch(MODULE + 'observations', side_effect=ValueError('model failure') if fail else None,
                                          return_value=[dict(status='unavailable_base')]))
                stack.enter_context(patch(MODULE + 'summarize', return_value=[]))
                if fail:
                    with self.assertRaisesRegex(ValueError, 'model failure'):
                        run(root, manifest, root / 'reference.json', root / 'unused.zip', root / 'output')
                else:
                    run(root, manifest, root / 'reference.json', root / 'unused.zip', root / 'output')
                report = json.loads((root / 'output/report.json').read_text())
                self.assertEqual(report['status'], 'failed' if fail else 'completed')
                self.assertEqual(report['native_replays'], 0)
                self.assertFalse(report['runtime_policy_changed'])
                self.assertFalse(report['installed_output_changed'])
                self.assertEqual(report['admission_acceptance'], 'not established')
                self.assertIn('finished_at', report)
